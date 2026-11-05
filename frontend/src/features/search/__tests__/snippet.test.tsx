import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderSnippet } from "../snippet";

describe("renderSnippet XSS safety & highlighting", () => {
  it("returns null for null, undefined, or empty string", () => {
    expect(renderSnippet(null)).toBeNull();
    expect(renderSnippet(undefined)).toBeNull();
    expect(renderSnippet("")).toBeNull();
  });

  it("renders plain text without marks normally", () => {
    const { container } = render(<div>{renderSnippet("Standard plain snippet text.")}</div>);
    expect(container.textContent).toBe("Standard plain snippet text.");
    expect(container.querySelector("mark")).toBeNull();
  });

  it("correctly identifies and highlights <mark> tokens", () => {
    const { container } = render(
      <div>
        {renderSnippet("Payment received for invoice <mark>INV-2026-001</mark> from vendor.")}
      </div>,
    );

    const markEl = container.querySelector("mark");
    expect(markEl).not.toBeNull();
    expect(markEl?.textContent).toBe("INV-2026-001");
    expect(container.textContent).toBe(
      "Payment received for invoice INV-2026-001 from vendor.",
    );
  });

  it("safely neutralizes malicious <script> tags as raw text without executing", () => {
    const payload =
      "Invoice text <script>alert('xss')</script> with <mark>highlight</mark>";
    const { container } = render(<div>{renderSnippet(payload)}</div>);

    // Absolutely no script element must exist in the DOM
    expect(container.querySelector("script")).toBeNull();
    // The script tag characters must be rendered literally as text
    expect(container.textContent).toContain("<script>alert('xss')</script>");
    // Mark should still work
    const markEl = container.querySelector("mark");
    expect(markEl?.textContent).toBe("highlight");
  });

  it("safely neutralizes malicious <img onerror=...> tags as text", () => {
    const payload =
      "Suspicious file <img src=x onerror=alert(1)> and match <mark>Acme</mark>";
    const { container } = render(<div>{renderSnippet(payload)}</div>);

    // No img element must exist in the DOM
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.querySelector("mark")?.textContent).toBe("Acme");
  });

  it("handles unbalanced or unclosed <mark> tags gracefully", () => {
    const { container } = render(
      <div>{renderSnippet("Unclosed tag <mark>highlighted until end")}</div>,
    );
    const markEl = container.querySelector("mark");
    expect(markEl).not.toBeNull();
    expect(markEl?.textContent).toBe("highlighted until end");
  });

  it("handles stray closing </mark> tags without error", () => {
    const { container } = render(
      <div>{renderSnippet("Stray closing </mark> followed by text")}</div>,
    );
    expect(container.textContent).toBe("Stray closing  followed by text");
    expect(container.querySelector("mark")).toBeNull();
  });
});
