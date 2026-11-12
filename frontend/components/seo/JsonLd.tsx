type JsonLdNode = Record<string, unknown>;

type JsonLdProps = {
  data: JsonLdNode | JsonLdNode[];
};

/** One document with `@context`. A raw array has no `@context` and breaks consumers that read it. */
function asJsonLdDocument(data: JsonLdNode | JsonLdNode[]): JsonLdNode {
  if (!Array.isArray(data)) return data;
  const graph = data.map((node) => {
    const rest = { ...node };
    delete rest["@context"];
    return rest;
  });
  return {
    "@context": "https://schema.org",
    "@graph": graph,
  };
}

export function JsonLd({ data }: JsonLdProps) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(asJsonLdDocument(data)) }}
    />
  );
}
