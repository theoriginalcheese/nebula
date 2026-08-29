import { ScrollViewStyleReset } from 'expo-router/html';
import type { ReactNode } from 'react';

/**
 * Root HTML for the web build. This file is web-only and runs in Node during
 * static rendering.
 *
 * The web target is not a fallback here — it is how the app gets onto the
 * phone. A free Apple account cannot sign an installable iOS build (that needs
 * the paid Developer Program), so the shipping route is "Add to Home Screen":
 * the tags below are what make iOS launch it fullscreen, with Nebula's own
 * icon and no Safari chrome, rather than as a web page.
 */
export default function Root({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        {/* viewport-fit=cover lets the layout reach under the notch and home
            indicator, which is what safe-area insets then account for. */}
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover, user-scalable=no"
        />

        {/* Launch standalone: own icon, own app-switcher card, no URL bar. */}
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-title" content="Nebula" />
        {/* black-translucent puts the status bar over the page, so the ambient
            backdrop runs to the top edge as it does in the frames. */}
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="theme-color" content="#0A0812" />
        {/* Files under mobile/public are copied to dist verbatim. Assets under
            assets/ are only bundled when code requires them, so the app icon
            has to live in public or the home-screen icon becomes a screenshot
            of the page. */}
        <link rel="apple-touch-icon" sizes="180x180" href="/icon-180.png" />
        <link rel="manifest" href="/manifest.webmanifest" />
        {/* Without a launch image iOS flashes blank on open — the clearest
            tell that a home-screen app is a web app. Sized for the 12 Pro. */}
        <link
          rel="apple-touch-startup-image"
          href="/splash-1170x2532.png"
          media="(device-width: 390px) and (device-height: 844px) and (-webkit-device-pixel-ratio: 3)"
        />

        {/*
          Disable body scrolling on web. This makes ScrollView components work
          closer to how they do on native.
        */}
        <ScrollViewStyleReset />

        {/* Escape-hatch so the page ground never flashes light before RN mounts. */}
        <style dangerouslySetInnerHTML={{ __html: rootBackground }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

// Nebula is a dark-only app (app.json userInterfaceStyle: "dark"), so the
// ground is --bg-page in both colour schemes — never the template's white.
// overscroll-behavior stops the rubber-band white flash at the scroll ends,
// which is the one thing that most gives away a home-screen web app.
const rootBackground = `
body {
  background-color: #0A0812;
  overscroll-behavior: none;
}
html {
  background-color: #0A0812;
  overscroll-behavior: none;
}
* {
  -webkit-tap-highlight-color: transparent;
  -webkit-touch-callout: none;
}
input, textarea {
  -webkit-user-select: text;
  user-select: text;
}`;
