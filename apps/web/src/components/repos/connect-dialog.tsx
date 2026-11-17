"use client";

import { FileArchive, GitBranch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, FieldHint, Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { formatBytes } from "@/lib/format";
import { wsPath } from "@/lib/navigation";
import { useConnectRepository, useSystemInfo, useUploadRepository } from "@/lib/queries";
import { useActiveWorkspace } from "@/lib/workspace-context";

type Source = "archive" | "git";

/** Connect a repository: upload an archive, or give an HTTPS git URL to clone. */
export function ConnectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { slug } = useActiveWorkspace();
  const router = useRouter();
  const system = useSystemInfo();
  const connect = useConnectRepository(slug, { silent: true });
  const upload = useUploadRepository(slug, { silent: true });
  const [source, setSource] = useState<Source>("archive");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const pending = connect.isPending || upload.isPending;
  const error = connect.error ?? upload.error;

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const created =
        source === "git"
          ? await connect.mutateAsync({
              git_url: url.trim(),
              branch: branch.trim() || undefined,
              name: name.trim() || undefined,
            })
          : file
            ? await upload.mutateAsync({ file, name: name.trim() || undefined })
            : null;
      if (!created) return;
      toast.success(`Indexing ${created.name}`);
      onOpenChange(false);
      router.push(wsPath(slug, "repos", encodeURIComponent(created.slug)));
    } catch {
      // Rendered from the mutation state.
    }
  }

  const ready = source === "git" ? url.trim().length > 11 : file !== null;
  const limit = system.data?.max_archive_mb ?? 100;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Connect a repository"
        description="CodeAgent reads the code to index it. It never pushes to a git host."
        className="w-[min(94vw,34rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <SegmentedControl<Source>
            label="Source"
            value={source}
            onValueChange={setSource}
            options={[
              {
                value: "archive",
                label: (
                  <>
                    <FileArchive /> Upload an archive
                  </>
                ),
              },
              {
                value: "git",
                label: (
                  <>
                    <GitBranch /> Git URL
                  </>
                ),
              },
            ]}
          />
          {source === "archive" ? (
            <Field
              label="Archive"
              htmlFor="repo-archive"
              hint={`A .zip, .tar.gz or .tgz of the repository, up to ${limit} MB.`}
              required
            >
              <input
                ref={input}
                id="repo-archive"
                type="file"
                accept=".zip,.tar,.tar.gz,.tgz,application/zip,application/gzip"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="border-input bg-card text-muted-foreground file:bg-muted file:text-foreground w-full rounded-lg border text-sm file:mr-3 file:cursor-pointer file:border-0 file:px-3 file:py-2 file:text-[13px] file:font-medium"
              />
              {file ? <FieldHint>{`${file.name}, ${formatBytes(file.size)}`}</FieldHint> : null}
            </Field>
          ) : (
            <>
              <Field
                label="Clone URL"
                htmlFor="repo-url"
                hint="HTTPS only, without credentials. Public repositories need none."
                required
              >
                <Input
                  id="repo-url"
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://github.com/owner/repository.git"
                  autoComplete="off"
                  required
                />
              </Field>
              <Field label="Branch" htmlFor="repo-branch" hint="Optional. Defaults to the remote's default branch.">
                <Input
                  id="repo-branch"
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  placeholder="main"
                />
              </Field>
            </>
          )}
          <Field label="Name" htmlFor="repo-name" hint="Optional. Taken from the file or URL when empty.">
            <Input id="repo-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} />
          </Field>
          {error ? <ErrorNotice message={error.message} /> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={pending} disabled={!ready}>
              Connect and index
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
