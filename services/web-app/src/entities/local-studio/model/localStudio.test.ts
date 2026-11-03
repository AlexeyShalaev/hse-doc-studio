import { describe, expect, it } from "vitest";
import {
  detectInstallOs,
  installCommand,
  manualCommand,
  type InstallInput,
} from "./install";
import {
  connectServerPath,
  localConnectUrl,
  localStudioPath,
  readConnectTarget,
  studioCloneUrl,
} from "./paths";

const ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b";
const BASE: InstallInput = {
  os: "macos",
  installBaseUrl:
    "https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy",
  image: "ghcr.io/alexeyshalaev/hse-doc-studio",
  serverUrl: "https://hse-doc-studio.ai-ops.ru",
  port: 17240,
  tag: null,
  lang: "ru",
};

describe("local studio paths", () => {
  it("keeps the stable routes and adds the project when given", () => {
    expect(localStudioPath()).toBe("/local-studio");
    expect(localStudioPath(ID)).toBe(`/local-studio?project=${ID}`);
    expect(connectServerPath()).toBe("/connect");
  });

  it("builds a deep link into the local Studio with the server and project", () => {
    const url = new URL(
      localConnectUrl(17241, "https://studio.example.org/", ID),
    );
    expect(url.origin).toBe("http://localhost:17241");
    expect(url.pathname).toBe("/connect");
    expect(url.searchParams.get("server")).toBe("https://studio.example.org");
    expect(url.searchParams.get("project")).toBe(ID);
  });

  it("reads the target back and drops a project that is not an id", () => {
    expect(
      readConnectTarget(
        new URLSearchParams(`server=https%3A%2F%2Fs.org&project=${ID}`),
      ),
    ).toEqual({ server: "https://s.org", projectId: ID });
    expect(
      readConnectTarget(new URLSearchParams("server=%20&project=../x")),
    ).toEqual({ server: null, projectId: null });
  });

  it("composes the clone address the server hands out", () => {
    expect(studioCloneUrl("https://s.org/", ID)).toBe(
      `https://s.org/git/${ID}.git`,
    );
  });
});

describe("install commands", () => {
  it("passes the server address to the sh script", () => {
    expect(installCommand(BASE)).toBe(
      "curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | HSE_STUDIO_LANG=ru HSE_STUDIO_CONNECT='https://hse-doc-studio.ai-ops.ru' sh",
    );
  });

  it("sets PowerShell variables on Windows, with port and tag when asked", () => {
    expect(
      installCommand({
        ...BASE,
        os: "windows",
        lang: "en",
        port: 18500,
        tag: "0.3",
      }),
    ).toBe(
      "$env:HSE_STUDIO_LANG='en'; $env:HSE_STUDIO_CONNECT='https://hse-doc-studio.ai-ops.ru'; $env:PORT='18500'; $env:TAG='0.3'; irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex",
    );
  });

  it("quotes a server address with a quote in it", () => {
    expect(installCommand({ ...BASE, serverUrl: "https://a'b" })).toContain(
      "HSE_STUDIO_CONNECT='https://a'\\''b'",
    );
  });

  it("uses the socket group on Linux in the manual command", () => {
    expect(manualCommand({ ...BASE, os: "linux", tag: "0.3" })).toContain(
      `--group-add "$(stat -c '%g' /var/run/docker.sock)"`,
    );
    expect(manualCommand(BASE)).toMatch(
      /-p 17240:8000 .*--group-add 0 .*hse-doc-studio:latest$/,
    );
  });

  it("detects the visitor's OS from the user agent", () => {
    expect(
      detectInstallOs("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"),
    ).toBe("windows");
    expect(
      detectInstallOs("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari"),
    ).toBe("macos");
    expect(detectInstallOs("Mozilla/5.0 (X11; Linux x86_64)")).toBe("linux");
  });
});
