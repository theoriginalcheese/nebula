"""The public iOS app and its build must not carry a private studio address.

    python tests/test_ios_public.py

The GitHub repo is public. Connection details are typed on the phone and
kept in the keychain. This fails if a tailnet name, a token, or a billed
Mac runner shows up in the app or the IPA workflow.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IOS = os.path.join(ROOT, "ios")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ios-ipa.yml")

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def files():
    found = []
    for base in (IOS,):
        for dirpath, _dirs, names in os.walk(base):
            for name in names:
                if name.endswith((".swift", ".plist", ".yml", ".json", ".md")):
                    found.append(os.path.join(dirpath, name))
    found.append(WORKFLOW)
    return found


TEXT = "\n".join(open(path, encoding="utf-8").read() for path in files())
LOWER = TEXT.lower()

for needle in (
    "tail25e601",
    "100.90.",
    "100.84.",
    "phone_agent_token",
    "obs_password",
    "mock-device",
    "akia",
    "begin openssh",
    "begin rsa",
):
    check("ios sources do not contain %s" % needle, needle not in LOWER)

workflow = open(WORKFLOW, encoding="utf-8").read()
check("the IPA job uses the free standard Mac runner",
      "runs-on: macos-latest" in workflow and "xlarge" not in workflow.lower())
check("the IPA job does not read GitHub secrets", "secrets." not in workflow)
check("the connection is stored in the keychain",
      "kSecClassGenericPassword" in TEXT and "UserDefaults" not in TEXT)
check("the token field is a secure field", "SecureField" in TEXT)
activity_plist = open(os.path.join(IOS, "Activity", "Info.plist"), encoding="utf-8").read()
check("the lock-screen widget has a version",
      "CFBundleVersion" in activity_plist and "CFBundleShortVersionString" in activity_plist)

passed_all = all(ok for _, ok, _ in results)
for name, ok, detail in results:
    print("%s  %-62s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%s (%d checks)" % ("ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
sys.exit(0 if passed_all else 1)
