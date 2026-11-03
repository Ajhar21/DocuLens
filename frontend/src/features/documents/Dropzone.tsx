import { forwardRef, useId, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import type { UploadPolicy } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface DropzoneProps {
  policy: UploadPolicy;
  disabled?: boolean;
  onFilesSelected: (files: File[]) => void;
}

export const Dropzone = forwardRef<HTMLButtonElement, DropzoneProps>(
  function Dropzone({ policy, disabled = false, onFilesSelected }, ref) {
    const inputRef = useRef<HTMLInputElement | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const hintId = useId();

    const formattedExtensions = policy.allowed_extensions
      .map((ext) => ext.replace(/^\./, "").toUpperCase())
      .join(", ");

    const handleTriggerClick = () => {
      if (disabled) return;
      inputRef.current?.click();
    };

    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = event.target.files;
      if (fileList && fileList.length > 0) {
        onFilesSelected(Array.from(fileList));
      }
      // Reset input value so selecting the same file again still triggers onChange
      event.target.value = "";
    };

    const handleDragOver = (event: React.DragEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      if (!disabled) {
        setIsDragOver(true);
      }
    };

    const handleDragLeave = (event: React.DragEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setIsDragOver(false);
    };

    const handleDrop = (event: React.DragEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setIsDragOver(false);
      if (disabled) return;
      const droppedFiles = event.dataTransfer.files;
      if (droppedFiles && droppedFiles.length > 0) {
        onFilesSelected(Array.from(droppedFiles));
      }
    };

    return (
      <div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={policy.allowed_extensions.join(",")}
          onChange={handleInputChange}
          disabled={disabled}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          data-testid="file-upload-input"
        />

        <button
          ref={ref}
          type="button"
          disabled={disabled}
          aria-describedby={hintId}
          onClick={handleTriggerClick}
          onDragOver={handleDragOver}
          onDragEnter={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          data-testid="upload-dropzone"
          className={cn(
            "group relative flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
            isDragOver
              ? "border-primary bg-primary/5"
              : "border-border bg-muted/20 hover:border-primary/60 hover:bg-muted/40",
          )}
        >
          <div
            className={cn(
              "mb-3 flex h-10 w-10 items-center justify-center rounded-full border bg-background transition-colors",
              isDragOver
                ? "border-primary text-primary"
                : "border-border text-muted-foreground group-hover:text-primary",
            )}
          >
            <UploadCloud className="h-5 w-5" />
          </div>

          <p className="text-sm font-medium text-foreground">
            <span className="text-primary underline-offset-4 group-hover:underline">
              Click to choose files
            </span>{" "}
            or drag and drop them here
          </p>

          <p id={hintId} className="mt-1 text-xs text-muted-foreground">
            Supported: {formattedExtensions} · Up to {policy.max_upload_mb} MB
            per file
          </p>
        </button>
      </div>
    );
  },
);

