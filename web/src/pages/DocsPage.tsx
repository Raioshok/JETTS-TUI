import { useLayoutEffect } from "react";
import { ArrowUpRight, BookOpen, ExternalLink } from "lucide-react";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn } from "@/lib/utils";
import { PluginSlot } from "@/plugins";

export const JETTS_TUI_DOCS_URL =
  "https://github.com/Raioshok/JETTS-TUI/tree/main/docs";

export const DOCS_LINKS = [
  { label: "Installation", path: "getting-started/installation.md" },
  { label: "Quickstart", path: "getting-started/quickstart.md" },
  { label: "Terminal UI", path: "user-guide/tui.md" },
  { label: "Configuration", path: "user-guide/configuration.md" },
  { label: "Messaging", path: "user-guide/messaging/index.md" },
  { label: "Integrations", path: "integrations/index.md" },
] as const;

const DS_BUTTON_OUTLINED_LINK_CN = cn(
  "group relative inline-grid grid-cols-[auto_1fr_auto] items-center",
  "px-[.9em_.75em] py-[1.25em] gap-2",
  "leading-0 font-bold tracking-[0.2em] uppercase",
  "text-midground bg-transparent shadow-midground",
  "shadow-[inset_-1px_-1px_0_0_#00000080,inset_1px_1px_0_0_#ffffff80]",
);

export default function DocsPage() {
  const { t } = useI18n();
  const { setEnd } = usePageHeader();

  useLayoutEffect(() => {
    setEnd(
      <a
        href={JETTS_TUI_DOCS_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={DS_BUTTON_OUTLINED_LINK_CN}
      >
        <ExternalLink className="size-3.5" />
        {t.app.openDocumentation}
      </a>,
    );
    return () => setEnd(null);
  }, [setEnd, t]);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
      <PluginSlot name="docs:top" />
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <div className="flex items-start gap-4 rounded-sm border border-current/20 p-5">
          <BookOpen className="mt-0.5 size-6 shrink-0" aria-hidden="true" />
          <h1 className="min-w-0 text-lg font-semibold">{t.app.nav.documentation}</h1>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {DOCS_LINKS.map(({ label, path }) => (
            <a
              key={path}
              href={`https://github.com/Raioshok/JETTS-TUI/blob/main/docs/${path}`}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex min-h-14 items-center justify-between gap-3 rounded-sm border border-current/20 px-4 py-3 transition-colors hover:bg-current/5 focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              <span className="font-medium">{label}</span>
              <ArrowUpRight
                className="size-4 shrink-0 text-midground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </a>
          ))}
        </div>
      </div>
      <PluginSlot name="docs:bottom" />
    </div>
  );
}
