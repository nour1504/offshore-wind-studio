import { Typography } from "@mantine/core";
import { marked } from "marked";
import { useMemo } from "react";

import { href } from "../router";

marked.setOptions({ gfm: true, breaks: false });

/**
 * Renders the application's own documentation (shipped with it, not user content).
 * Links written as "doc:topic-id" open another help topic.
 */
export function Markdown({ text }: { text: string }) {
  const html = useMemo(() => {
    const rendered = marked.parse(text, { async: false });
    return rendered.replace(/href="doc:([\w./-]+)"/g, (_, id: string) => `href="${href(`help/${id}`)}"`);
  }, [text]);
  return (
    <Typography>
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </Typography>
  );
}
