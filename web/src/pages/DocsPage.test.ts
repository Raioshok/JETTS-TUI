import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DOCS_LINKS, JETTS_TUI_DOCS_URL } from "./DocsPage";

describe("dashboard documentation links", () => {
  it("points every entry at a Markdown guide shipped with the repository", () => {
    expect(JETTS_TUI_DOCS_URL).toBe(
      "https://github.com/Raioshok/JETTS-TUI/tree/main/docs",
    );
    expect(DOCS_LINKS.length).toBeGreaterThan(0);
    for (const { path } of DOCS_LINKS) {
      expect(path).toMatch(/\.md$/);
      expect(existsSync(resolve(process.cwd(), "..", "docs", path))).toBe(true);
    }
  });
});
