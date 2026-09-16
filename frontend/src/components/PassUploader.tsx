import {useRef, useState} from "react";
import {FolderOpen, Trash2, Upload} from "lucide-react";
import {deletePass, uploadPass} from "../lib/oiltrace";

export interface PassUploaderProps {
  /** Passes already on disk, so the shipped three can be protected. */
  existing: string[];
  /** Called with the new pass id once it has been written. */
  onCreated: (snapshotId: string) => void;
  onDeleted: (snapshotId: string) => void;
  busy: boolean;
}

/** t1-t3 ship with the repo; anything above them was uploaded here. */
const SHIPPED = new Set(["t1", "t2", "t3"]);

/**
 * Drop a folder of SAR tiles in and get the next pass out.
 *
 * This is the demo's live input: images arrive the way a downlink would deliver
 * them, the pass is created, and the pipeline runs over it. Nothing about the
 * images is configured or labelled — the classifier sees the bytes, and because
 * an uploaded pass has no ground truth, the summary says so rather than
 * implying the result was checked against something.
 */
export function PassUploader({existing, onCreated, onDeleted, busy}: PassUploaderProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [sending, setSending] = useState(false);

  const uploaded = existing.filter((id) => !SHIPPED.has(id));

  const send = async (files: File[]) => {
    const images = files.filter((f) => /\.(jpe?g|png|tiff?|bmp)$/i.test(f.name));
    if (!images.length) {
      setStatus("No images in that drop — expected .jpg, .png, .tif or .bmp.");
      setResult(null);
      return;
    }
    setSending(true);
    setStatus(`Uploading ${images.length} tile${images.length === 1 ? "" : "s"}…`);
    setResult(null);
    const res = await uploadPass(images);
    setSending(false);
    if (!res || res.error) {
      setStatus(res?.error ?? "Upload failed.");
      return;
    }
    setResult(res);
    setStatus(null);
    onCreated(res.snapshot_id);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (busy || sending) return;
    send(Array.from(e.dataTransfer.files));
  };

  const remove = async (id: string) => {
    const res = await deletePass(id);
    if (res?.error) { setStatus(res.error); return; }
    setResult(null);
    setStatus(`Removed ${id.toUpperCase()}.`);
    onDeleted(id);
  };

  return (
    <div className="uploader">
      <div
        className={"dropzone" + (dragging ? " over" : "") + (sending ? " sending" : "")}
        onDragOver={(e) => { e.preventDefault(); if (!busy && !sending) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <div>
          <b><Upload size={13} /> Add SAR observation</b>
          <small>JPG · PNG · TIFF · BMP</small>
        </div>
        <div className="dropactions">
          <button onClick={() => folderRef.current?.click()} disabled={busy || sending}>
            <FolderOpen size={13} /> Folder
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={busy || sending}>
            Files
          </button>
        </div>
      </div>

      {/* webkitdirectory is not in React's typings but is what makes the picker
          select a whole folder, which is how the demo actually feeds this. */}
      <input
        ref={folderRef} type="file" multiple hidden accept="image/*"
        {...({webkitdirectory: "", directory: ""} as any)}
        onChange={(e) => { send(Array.from(e.target.files || [])); e.target.value = ""; }}
      />
      <input
        ref={fileRef} type="file" multiple hidden accept="image/*"
        onChange={(e) => { send(Array.from(e.target.files || [])); e.target.value = ""; }}
      />

      {status && <div className="uploadstatus">{status}</div>}

      {result && (
        <div className="uploadresult">
          <b>{String(result.snapshot_id).toUpperCase()} created — {result.images_written} tiles</b>
          <ul>
            {result.assignments.map((a: any) => (
              <li key={a.ship_id}>{a.ship_name} ← {a.source_filename}</li>
            ))}
          </ul>
          {result.vessels_without_tile?.length > 0 && (
            <small>No tile this pass: {result.vessels_without_tile.join(", ")}.</small>
          )}
          {result.images_ignored?.length > 0 && (
            <small>Ignored past the roster: {result.images_ignored.join(", ")}.</small>
          )}
          {result.rejected?.length > 0 && (
            <small className="warn">
              Rejected: {result.rejected.map((r: any) => `${r.filename} (${r.reason})`).join(", ")}.
            </small>
          )}
          <small className="warn">
            Paired in filename order — chosen here, not observed. No ground truth exists
            for an uploaded pass, so the model's call on these tiles has nothing to be
            checked against.
          </small>
        </div>
      )}

      {uploaded.length > 0 && (
        <div className="uploadedlist">
          {uploaded.map((id) => (
            <span key={id}>
              {id.toUpperCase()}
              <button onClick={() => remove(id)} title={`Delete ${id.toUpperCase()}`}
                      aria-label={`Delete pass ${id.toUpperCase()}`}>
                <Trash2 size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
