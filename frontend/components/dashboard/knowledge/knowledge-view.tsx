"use client";

import { FileText, Loader2, RefreshCw, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useDeleteKnowledgeDocument, useKnowledgeDocuments, useUploadKnowledgeDocument } from "@/hooks/api/use-knowledge";

export function KnowledgeView() {
  const inputRef = useRef<HTMLInputElement>(null);
  const documents = useKnowledgeDocuments();
  const upload = useUploadKnowledgeDocument();
  const remove = useDeleteKnowledgeDocument();
  const [progress, setProgress] = useState(0);

  async function selectFile(file?: File) {
    if (!file) return;
    setProgress(0);
    try {
      await upload.mutateAsync({ file, onProgress: setProgress });
      toast.success("Document uploaded");
    } catch { toast.error("Unable to upload document"); }
    finally { if (inputRef.current) inputRef.current.value = ""; }
  }

  async function deleteDocument(id: string, name: string) {
    if (!window.confirm(`Delete ${name}?`)) return;
    try { await remove.mutateAsync(id); toast.success("Document deleted"); }
    catch { toast.error("Unable to delete document"); }
  }

  return <div className="space-y-6">
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div><h1 className="text-2xl font-semibold">Knowledge Base</h1><p className="mt-1 text-sm text-muted-foreground">Manage documents for future knowledge retrieval.</p></div>
      <Button onClick={() => inputRef.current?.click()} disabled={upload.isPending}>{upload.isPending ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}Upload document</Button>
      <input ref={inputRef} type="file" accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(event) => selectFile(event.target.files?.[0])} />
    </div>
    {upload.isPending && <div className="rounded-xl border p-4"><div className="mb-2 flex justify-between text-sm"><span>Uploading</span><span>{progress}%</span></div><div className="h-2 rounded-full bg-muted"><div className="h-full rounded-full bg-brand" style={{ width: `${progress}%` }} /></div></div>}
    {documents.isLoading ? <div className="flex justify-center py-16"><Loader2 className="size-6 animate-spin" /></div> : documents.isError ? <div className="rounded-xl border p-8 text-center"><p className="mb-4 text-sm text-destructive">Unable to load documents.</p><Button variant="outline" onClick={() => documents.refetch()}><RefreshCw className="size-4" />Retry</Button></div> : !documents.data?.items.length ? <div className="rounded-xl border border-dashed p-12 text-center"><FileText className="mx-auto mb-4 size-10 text-muted-foreground" /><h2 className="font-medium">No documents yet</h2><p className="mt-1 text-sm text-muted-foreground">Upload PDF, DOCX, TXT, or Markdown files.</p></div> : <div className="overflow-x-auto rounded-xl border bg-card"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/40 text-muted-foreground"><tr>{["Name","Type","Size","Status","Uploaded","Actions"].map((label) => <th key={label} className="px-4 py-3">{label}</th>)}</tr></thead><tbody>{documents.data.items.map((document) => <tr key={document.id} className="border-b last:border-0"><td className="px-4 py-3 font-medium">{document.title}</td><td className="px-4 py-3">{document.original_filename.split(".").pop()?.toUpperCase()}</td><td className="px-4 py-3">{formatBytes(document.file_size)}</td><td className="px-4 py-3">{document.status}</td><td className="px-4 py-3">{new Date(document.created_at).toLocaleDateString()}</td><td className="px-4 py-3"><Button size="icon" variant="ghost" aria-label={`Delete ${document.title}`} onClick={() => deleteDocument(document.id, document.title)}><Trash2 className="size-4" /></Button></td></tr>)}</tbody></table></div>}
  </div>;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
