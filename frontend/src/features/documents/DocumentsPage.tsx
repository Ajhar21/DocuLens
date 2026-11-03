import { useRef } from "react";
import { canUploadDocuments } from "@/features/auth/roles";
import { useAuth } from "@/features/auth/use-auth";
import { DocumentTable } from "./DocumentTable";
import { UploadPanel } from "./UploadPanel";

export function DocumentsPage() {
  const { user } = useAuth();
  const dropzoneButtonRef = useRef<HTMLButtonElement | null>(null);

  const allowUpload = user ? canUploadDocuments(user.role) : false;

  const handleFocusUpload = () => {
    dropzoneButtonRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
    dropzoneButtonRef.current?.focus();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Documents
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {allowUpload
            ? "Upload financial documents in batches and monitor real-time parsing status."
            : "Browse uploaded documents and track their extraction status."}
        </p>
      </div>

      {allowUpload && <UploadPanel ref={dropzoneButtonRef} />}

      <DocumentTable
        canUpload={allowUpload}
        onFocusUpload={allowUpload ? handleFocusUpload : undefined}
      />
    </div>
  );
}

