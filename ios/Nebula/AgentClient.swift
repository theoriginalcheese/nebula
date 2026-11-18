import Foundation

/// One WebSocket to the studio PC. The token is sent in `hello` and never logged.
final class AgentClient {
    var onEvent: ((String, [String: Any]) -> Void)?
    var onRejected: (() -> Void)?
    var onDrop: (() -> Void)?
    var onRecovered: (() -> Void)?

    private let queue = DispatchQueue(label: "app.nebula.mobile.agent")
    private var session: URLSession?
    private var task: URLSessionWebSocketTask?
    private var endpoint: StudioEndpoint?
    private var stopped = true
    private var attempt = 0
    private var reconnecting = false
    private var waiters: [String: (Result<[String: Any], String>) -> Void] = [:]

    func start(_ endpoint: StudioEndpoint) {
        queue.async {
            self.endpoint = endpoint
            self.stopped = false
            self.attempt = 0
            self.open()
        }
    }

    func stop() {
        queue.async {
            self.stopped = true
            self.reconnecting = false
            self.failWaiters("Studio PC is offline.")
            self.task?.cancel(with: .goingAway, reason: nil)
            self.task = nil
            self.session?.invalidateAndCancel()
            self.session = nil
        }
    }

    func send(_ type: String, data: [String: Any] = [:], reply: ((Result<[String: Any], String>) -> Void)? = nil) {
        queue.async {
            guard !self.stopped, let task = self.task else {
                if let reply {
                    DispatchQueue.main.async { reply(.failure("Studio PC is offline.")) }
                }
                return
            }
            let id = UUID().uuidString
            if let reply {
                self.waiters[id] = reply
                self.queue.asyncAfter(deadline: .now() + 8) {
                    self.finish(id, .failure("Studio PC didn’t answer."))
                }
            }
            let body: [String: Any] = ["type": type, "id": id, "data": data]
            guard let encoded = try? JSONSerialization.data(withJSONObject: body),
                  let text = String(data: encoded, encoding: .utf8)
            else {
                self.finish(id, .failure("Could not send that."))
                return
            }
            task.send(.string(text)) { [weak self] error in
                guard let self, error != nil else { return }
                self.queue.async {
                    self.finish(id, .failure("Studio PC is offline."))
                    self.fail(task)
                }
            }
        }
    }

    private func open() {
        guard !stopped, let endpoint, let url = endpoint.socketURL else { return }
        task?.cancel(with: .goingAway, reason: nil)
        session?.invalidateAndCancel()
        let session = URLSession(configuration: .ephemeral)
        self.session = session
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()
        listen(task)
        sendHello(on: task, token: endpoint.token)
    }

    private func sendHello(on task: URLSessionWebSocketTask, token: String) {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0"
        let body: [String: Any] = [
            "type": "hello",
            "id": UUID().uuidString,
            "data": ["deviceToken": token, "appVersion": version],
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body),
              let text = String(data: data, encoding: .utf8)
        else { return }
        task.send(.string(text)) { [weak self] error in
            guard let self, error != nil else { return }
            self.queue.async { self.fail(task) }
        }
    }

    private func listen(_ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self else { return }
            self.queue.async {
                guard self.task === task, !self.stopped else { return }
                switch result {
                case let .success(message):
                    self.attempt = 0
                    self.ingest(message)
                    self.listen(task)
                case .failure:
                    self.fail(task)
                }
            }
        }
    }

    private func ingest(_ message: URLSessionWebSocketTask.Message) {
        let text: String?
        switch message {
        case let .string(value):
            text = value
        case let .data(value):
            text = String(data: value, encoding: .utf8)
        }
        guard let text,
              let data = text.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String
        else { return }
        let payload = object["data"] as? [String: Any] ?? [:]
        let id = object["id"] as? String
        if type == "error" {
            let code = payload["code"] as? String ?? ""
            let message = payload["message"] as? String ?? "Studio PC refused that."
            if code == "unauthorised" {
                stopped = true
                failWaiters(message)
                DispatchQueue.main.async { [weak self] in self?.onRejected?() }
                return
            }
            finish(id, .failure(message))
            return
        }
        if type == "ack" {
            finish(id, .success(payload))
        }
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.onRecovered?()
            if type != "ack" {
                self.onEvent?(type, payload)
            }
        }
    }

    private func finish(_ id: String?, _ result: Result<[String: Any], String>) {
        guard let id, let waiter = waiters.removeValue(forKey: id) else { return }
        DispatchQueue.main.async { waiter(result) }
    }

    private func failWaiters(_ message: String) {
        let pending = waiters
        waiters.removeAll()
        DispatchQueue.main.async {
            pending.values.forEach { $0(.failure(message)) }
        }
    }

    private func fail(_ task: URLSessionWebSocketTask) {
        guard self.task === task, !stopped else { return }
        self.task = nil
        failWaiters("Studio PC is offline.")
        DispatchQueue.main.async { [weak self] in self?.onDrop?() }
        schedule()
    }

    private func schedule() {
        guard !stopped, !reconnecting else { return }
        reconnecting = true
        let delay = min(15.0, 0.5 * pow(2.0, Double(attempt)))
        attempt += 1
        queue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self else { return }
            self.reconnecting = false
            guard !self.stopped else { return }
            self.open()
        }
    }
}
