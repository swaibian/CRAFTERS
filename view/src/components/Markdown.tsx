/**
 * Markdown renderer: GFM tables/code preferred (react-markdown + remark-gfm).
 *
 * Why (SW-REQ-CHAT): streamed agent replies are markdown with code blocks and
 * tables; rendering must not execute HTML (rehype-raw deliberately absent).
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
