import { useState, useEffect } from "react";

interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  status: string;
}

interface Case {
  id: string;
  case_number: string;
  title: string;
  description: string | null;
  status: string;
  created_by: string;
}

interface CaseParticipant {
  id: string;
  case_id: string;
  user_id: string;
  role: string;
  joined_at: string;
  display_name: string | null;
  email: string;
}

interface CaseDetail extends Case {
  participants: CaseParticipant[];
}

interface DocumentVersion {
  id: string;
  version_number: number;
  sha256_hash: string;
  parent_version_id: string | null;
  opaque_verification_id: string;
  blockchain_status: "pending" | "submitted" | "confirmed" | "failed";
  blockchain_tx_hash: string | null;
  blockchain_block_number: number | null;
  blockchain_timestamp: string | null;
  created_at: string;
  public_verification_url: string;
}

interface DocumentInfo {
  id: string;
  case_id: string;
  title: string;
  document_type: string;
  owner_user_id: string;
  current_version_id: string;
  classification: string;
  created_at: string;
  updated_at: string;
  versions: DocumentVersion[];
}

interface DocumentGrant {
  id: string;
  document_id: string;
  version_id: string;
  version_number?: number;
  granted_to_user_id: string;
  granted_to_email?: string;
  granted_to_name?: string;
  permission: "VIEW" | "DOWNLOAD";
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

interface AuditEvent {
  id: string;
  event_type: string;
  created_at: string;
  actor_type: string;
  details: any;
  actor_user_id?: string;
}

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [user, setUser] = useState<UserProfile | null>(null);
  const [view, setView] = useState<"login" | "register" | "dashboard" | "case_detail" | "verify_public">("login");
  const [cases, setCases] = useState<Case[]>([]);
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);

  // M2-M6 State Variables
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocumentInfo | null>(null);
  const [docTab, setDocTab] = useState<"passport" | "grants" | "audit" | "new_version">("passport");
  const [grants, setGrants] = useState<DocumentGrant[]>([]);
  const [docAudit, setDocAudit] = useState<AuditEvent[]>([]);

  // Public matching states
  const [publicOpaqueId, setPublicOpaqueId] = useState<string | null>(null);
  const [verificationResult, setVerificationResult] = useState<{
    status: "VERIFIED" | "INTEGRITY_FAILURE" | "RECORD_NOT_FOUND" | "VERIFICATION_UNAVAILABLE";
    blockchain_timestamp?: string | null;
    blockchain_block_number?: number | null;
    blockchain_tx_hash?: string | null;
    candidate_hash?: string;
    details?: string;
  } | null>(null);
  const [verifyingFile, setVerifyingFile] = useState(false);

  // Forms State
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState("LAWYER");

  const [newCaseNumber, setNewCaseNumber] = useState("");
  const [newCaseTitle, setNewCaseTitle] = useState("");
  const [newCaseDesc, setNewCaseDesc] = useState("");

  const [partUserId, setPartUserId] = useState("");
  const [partRole, setPartRole] = useState("client");

  // Document creation form
  const [docTitle, setDocTitle] = useState("");
  const [docType, setDocType] = useState("pleading");
  const [docFile, setDocFile] = useState<File | null>(null);

  // Grant access form
  const [grantToUserId, setGrantToUserId] = useState("");
  const [grantPermission, setGrantPermission] = useState<"VIEW" | "DOWNLOAD">("VIEW");
  const [grantExpiryMins, setGrantExpiryMins] = useState("");

  // New version form
  const [verFile, setVerFile] = useState<File | null>(null);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const BACKEND_URL = "http://localhost:8000/api/v1";

  // Web Crypto Helper for SHA-256 calculation
  const calculateSHA256 = async (file: File): Promise<string> => {
    const arrayBuffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
  };

  // Route routing mapping on load and state change
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname;
      if (path.startsWith("/verify/public/")) {
        const opaqueId = path.split("/verify/public/")[1];
        if (opaqueId) {
          setPublicOpaqueId(opaqueId);
          setView("verify_public");
        }
      } else {
        if (token) {
          setView("dashboard");
          fetchUser(token);
        } else {
          setView("login");
        }
      }
    };
    window.addEventListener("popstate", handlePopState);
    handlePopState();
    return () => window.removeEventListener("popstate", handlePopState);
  }, [token]);

  const navigateTo = (newView: "login" | "register" | "dashboard" | "case_detail" | "verify_public", opaqueId?: string) => {
    setErrorMsg(null);
    setSuccessMsg(null);
    if (newView === "verify_public" && opaqueId) {
      window.history.pushState({}, "", `/verify/public/${opaqueId}`);
      setPublicOpaqueId(opaqueId);
      setView("verify_public");
    } else {
      window.history.pushState({}, "", "/");
      setPublicOpaqueId(null);
      setVerificationResult(null);
      setView(newView);
    }
  };

  const fetchUser = async (authToken: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
        fetchCases(authToken);
      } else {
        handleLogout();
      }
    } catch {
      setErrorMsg("Failed to connect to authentication server.");
      handleLogout();
    }
  };

  const fetchCases = async (authToken: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/cases`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCases(data);
      }
    } catch (err: any) {
      setErrorMsg(`Failed to fetch cases: ${err.message}`);
    }
  };

  const fetchCaseDetail = async (caseId: string) => {
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/cases/${caseId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCaseDetail(data);
        fetchDocuments(caseId);
        navigateTo("case_detail");
      } else {
        setErrorMsg("Failed to retrieve case details. Access denied or case not found (404).");
      }
    } catch (err: any) {
      setErrorMsg(`Error loading case: ${err.message}`);
    }
  };

  const fetchDocuments = async (caseId: string) => {
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/cases/${caseId}/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err: any) {
      setErrorMsg(`Failed to fetch documents: ${err.message}`);
    }
  };

  const fetchDocumentPassport = async (docId: string) => {
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/documents/${docId}/passport`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const passportData = await res.json();
        // Backend returns document_id; frontend DocumentInfo interface uses id.
        // Normalize so all downstream selectedDoc.id calls work correctly.
        if (passportData.document_id && !passportData.id) {
          passportData.id = passportData.document_id;
        }
        // Normalize current_version_id from latest version if missing
        if (!passportData.current_version_id && passportData.versions && passportData.versions.length > 0) {
          const sorted = [...passportData.versions].sort((a: any, b: any) => b.version_number - a.version_number);
          passportData.current_version_id = sorted[0].id;
        }
        setSelectedDoc(passportData);
        // Refresh sub views
        fetchDocumentGrants(docId);
        fetchDocumentAudit(docId);
      } else {
        setErrorMsg("Failed to retrieve document passport evidence record.");
      }
    } catch (err: any) {
      setErrorMsg(`Error loading document passport: ${err.message}`);
    }
  };

  const fetchDocumentGrants = async (docId: string) => {
    if (!token) return;
    try {
      // Backend route is /documents/{id}/access (not /grants)
      const res = await fetch(`${BACKEND_URL}/documents/${docId}/access`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setGrants(data);
      }
    } catch (err: any) {
      setErrorMsg(`Failed to fetch access grants: ${err.message}`);
    }
  };

  const fetchDocumentAudit = async (docId: string) => {
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/documents/${docId}/audit`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setDocAudit(data);
      }
    } catch (err: any) {
      setErrorMsg(`Failed to retrieve document audit logs: ${err.message}`);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, display_name: displayName || null, role }),
      });
      const data = await res.json();
      if (res.ok) {
        setSuccessMsg("Registration successful! Please login.");
        navigateTo("login");
      } else {
        setErrorMsg(data.detail || "Registration failed.");
      }
    } catch (err: any) {
      setErrorMsg(`Failed to register: ${err.message}`);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (res.ok) {
        localStorage.setItem("token", data.access_token);
        setToken(data.access_token);
        fetchUser(data.access_token);
      } else {
        setErrorMsg(data.detail || "Login failed.");
      }
    } catch (err: any) {
      setErrorMsg(`Failed to login: ${err.message}`);
    }
  };

  const handleDemoLogin = async (demoRole: string) => {
    setErrorMsg(null);
    setSuccessMsg(null);
    const demoEmail = `${demoRole.toLowerCase()}@evault.demo`;
    const demoPass = "demopassword123";

    try {
      await fetch(`${BACKEND_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: demoEmail,
          password: demoPass,
          display_name: `Demo ${demoRole.charAt(0) + demoRole.slice(1).toLowerCase()}`,
          role: demoRole,
        }),
      });

      const loginRes = await fetch(`${BACKEND_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: demoEmail, password: demoPass }),
      });
      const loginData = await loginRes.json();
      if (loginRes.ok) {
        localStorage.setItem("token", loginData.access_token);
        setToken(loginData.access_token);
        fetchUser(loginData.access_token);
      } else {
        setErrorMsg(loginData.detail || "Demo login failed.");
      }
    } catch (err: any) {
      setErrorMsg(`Demo login failure: ${err.message}`);
    }
  };

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/cases`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          case_number: newCaseNumber,
          title: newCaseTitle,
          description: newCaseDesc || null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setSuccessMsg(`Case ${data.case_number} created successfully.`);
        setNewCaseNumber("");
        setNewCaseTitle("");
        setNewCaseDesc("");
        fetchCases(token);
      } else {
        setErrorMsg(data.detail || "Failed to create case.");
      }
    } catch (err: any) {
      setErrorMsg(`Create case error: ${err.message}`);
    }
  };

  const handleAddParticipant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !caseDetail) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/cases/${caseDetail.id}/participants`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          user_id: partUserId,
          role: partRole,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setSuccessMsg(`Participant added successfully.`);
        setPartUserId("");
        fetchCaseDetail(caseDetail.id);
      } else {
        setErrorMsg(data.detail || "Failed to add participant.");
      }
    } catch (err: any) {
      setErrorMsg(`Add participant error: ${err.message}`);
    }
  };

  const handleUploadDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !caseDetail || !docFile) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const formData = new FormData();
      formData.append("file", docFile);
      formData.append("title", docTitle);
      formData.append("document_type", docType);

      // Generate random uuid as client-side idempotency-key
      const idempotencyKey = crypto.randomUUID();

      const res = await fetch(`${BACKEND_URL}/cases/${caseDetail.id}/documents`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "X-Idempotency-Key": idempotencyKey
        },
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setSuccessMsg(`Document "${data.title}" registered successfully.`);
        setDocTitle("");
        setDocFile(null);
        // Clear input element
        const fileInput = document.getElementById("doc-file-input") as HTMLInputElement;
        if (fileInput) fileInput.value = "";
        fetchDocuments(caseDetail.id);
      } else {
        setErrorMsg(data.detail || "Upload failed.");
      }
    } catch (err: any) {
      setErrorMsg(`Upload error: ${err.message}`);
    }
  };

  const handleUploadVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedDoc || !verFile) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const formData = new FormData();
      formData.append("file", verFile);

      const idempotencyKey = crypto.randomUUID();

      const res = await fetch(`${BACKEND_URL}/documents/${selectedDoc.id}/versions`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "X-Idempotency-Key": idempotencyKey
        },
        body: formData
      });
      if (res.ok) {
        setSuccessMsg("New version committed and anchored successfully.");
        setVerFile(null);
        const verInput = document.getElementById("ver-file-input") as HTMLInputElement;
        if (verInput) verInput.value = "";
        fetchDocumentPassport(selectedDoc.id);
        if (caseDetail) fetchDocuments(caseDetail.id);
      } else {
        const errData = await res.json();
        setErrorMsg(errData.detail || "Failed to commit version.");
      }
    } catch (err: any) {
      setErrorMsg(`Version upload error: ${err.message}`);
    }
  };

  const handleGrantAccess = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedDoc) return;
    setErrorMsg(null);
    setSuccessMsg(null);

    // Get selected version (current latest)
    const versionId = selectedDoc.current_version_id;

    try {
      const payload: any = {
        granted_to_user_id: grantToUserId,
        permission: grantPermission
      };

      if (grantExpiryMins) {
        const expDate = new Date();
        expDate.setMinutes(expDate.getMinutes() + parseInt(grantExpiryMins));
        payload.expires_at = expDate.toISOString();
      }

      const res = await fetch(`${BACKEND_URL}/documents/${selectedDoc.id}/versions/${versionId}/access`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setSuccessMsg("Access grant registered successfully.");
        setGrantToUserId("");
        setGrantExpiryMins("");
        fetchDocumentGrants(selectedDoc.id);
      } else {
        const errData = await res.json();
        setErrorMsg(errData.detail || "Failed to grant access.");
      }
    } catch (err: any) {
      setErrorMsg(`Grant access error: ${err.message}`);
    }
  };

  const handleRevokeGrant = async (grantId: string) => {
    if (!token || !selectedDoc) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/documents/${selectedDoc.id}/access/${grantId}/revoke`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setSuccessMsg("Access grant revoked permanently.");
        fetchDocumentGrants(selectedDoc.id);
      } else {
        const errData = await res.json();
        setErrorMsg(errData.detail || "Failed to revoke access.");
      }
    } catch (err: any) {
      setErrorMsg(`Revocation error: ${err.message}`);
    }
  };

  const handleDownloadFile = async (versionId: string, versionNumber: number) => {
    if (!token || !selectedDoc) return;
    setErrorMsg(null);
    try {
      const res = await fetch(`${BACKEND_URL}/documents/${selectedDoc.id}/versions/${versionId}/download`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${selectedDoc.title}_v${versionNumber}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        const errData = await res.json();
        setErrorMsg(errData.detail || "Failed to download version file. Access Denied.");
      }
    } catch (err: any) {
      setErrorMsg(`Download error: ${err.message}`);
    }
  };

  // Drag and drop local verification file handler
  const handleVerifyFileLocal = async (file: File, opaqueId: string, isPublic: boolean = false) => {
    setVerifyingFile(true);
    setVerificationResult(null);
    setErrorMsg(null);

    // M2 PDF Validation checks
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setVerificationResult({
        status: "INTEGRITY_FAILURE",
        details: "Security Validation Check: File rejected. Invalid extension (Only .pdf files are accepted)."
      });
      setVerifyingFile(false);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setVerificationResult({
        status: "INTEGRITY_FAILURE",
        details: "Security Validation Check: File rejected. Exceeds max payload threshold (10MB)."
      });
      setVerifyingFile(false);
      return;
    }

    try {
      // Magic bytes check (first 5 bytes must be %PDF-)
      const slice = file.slice(0, 5);
      const reader = new FileReader();
      reader.onload = async () => {
        const bytes = new Uint8Array(reader.result as ArrayBuffer);
        const signature = String.fromCharCode(...bytes);
        if (signature !== "%PDF-") {
          setVerificationResult({
            status: "INTEGRITY_FAILURE",
            details: "Security Validation Check: File rejected. Invalid magic bytes signature (File is not a valid PDF)."
          });
          setVerifyingFile(false);
          return;
        }

        // Calculate candidate SHA-256 hash locally
        const candidateHash = await calculateSHA256(file);

        // Make API request to matching endpoint.
        // Public path: POST /verify/public/{opaqueId} with multipart file only.
        // Authenticated path: POST /verify with file + document_id + version_id form fields.
        const url = isPublic
          ? `${BACKEND_URL}/verify/public/${opaqueId}`
          : `${BACKEND_URL}/verify`;

        const headers: any = {};
        if (!isPublic && token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        // Build the correct FormData for each path
        const requestBody = (() => {
          const fd = new FormData();
          // Append with explicit application/pdf type so backend content_type check passes
          fd.append("file", file, file.name);
          if (!isPublic && selectedDoc) {
            fd.append("document_id", selectedDoc.id);
            const matchingVer = selectedDoc.versions?.find(
              (v: any) => v.opaque_verification_id === opaqueId
            );
            if (matchingVer) {
              fd.append("version_id", matchingVer.id);
            }
          }
          return fd;
        })();

        const verifyRes = await fetch(url, {
          method: "POST",
          headers,
          body: requestBody,
        });

        if (verifyRes.ok) {
          const verifyData = await verifyRes.json();
          // Backend returns block_number / timestamp; normalize to UI field names
          setVerificationResult({
            status: verifyData.status,
            blockchain_timestamp: verifyData.blockchain_timestamp ?? (
              verifyData.timestamp ? new Date(verifyData.timestamp * 1000).toISOString() : null
            ),
            blockchain_block_number: verifyData.blockchain_block_number ?? verifyData.block_number ?? null,
            blockchain_tx_hash: verifyData.blockchain_tx_hash ?? null,
            candidate_hash: candidateHash,
            details:
              verifyData.status === "VERIFIED"
                ? "✓ Valid record match confirmed on blockchain ledger."
                : verifyData.status === "INTEGRITY_FAILURE"
                ? "⚠ Hash Mismatch: Local file content has been altered or does not match this registered version."
                : verifyData.status === "VERIFICATION_UNAVAILABLE"
                ? "⚠ Blockchain ledger registry is currently unreachable. Verification cannot be performed."
                : "⚠ Opaque identifier is not recognized on file.",
          });
        } else if (verifyRes.status === 429) {
          setVerificationResult({
            status: "VERIFICATION_UNAVAILABLE",
            details: "Rate limit exceeded. Please wait a minute before verifying again.",
          });
        } else {
          const errData = await verifyRes.json().catch(() => ({}));
          setVerificationResult({
            status: "RECORD_NOT_FOUND",
            details: errData.detail || errData.message || "Provenance record not found.",
          });
        }
        setVerifyingFile(false);
      };
      reader.readAsArrayBuffer(slice);

    } catch (err: any) {
      setErrorMsg(`Verification process failed: ${err.message}`);
      setVerifyingFile(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    setCases([]);
    setCaseDetail(null);
    setSelectedDoc(null);
    navigateTo("login");
  };

  // Lead lawyer / case creator access checker
  const isLead = () => {
    if (!user || !caseDetail) return false;
    const creatorCheck = caseDetail.created_by === user.id;
    const roleCheck = caseDetail.participants.some(
      (p) => p.user_id === user.id && p.role === "lead_lawyer"
    );
    return creatorCheck || roleCheck;
  };

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "30px 20px" }}>
      
      {/* Top Banner and Navigation bar */}
      <header className="glass-panel" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "40px", padding: "16px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", cursor: "pointer" }} onClick={() => navigateTo(token ? "dashboard" : "login")}>
          <div style={{ width: "32px", height: "32px", borderRadius: "8px", background: "linear-gradient(135deg, var(--color-primary), var(--color-neutral))", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "bold", fontSize: "18px" }}>V</div>
          <span style={{ fontSize: "20px", fontWeight: "700", fontFamily: "Outfit, sans-serif" }}>Legal eVault</span>
        </div>
        {user && (
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "14px", fontWeight: "600" }}>{user.display_name || "Case Participant"}</div>
              <div style={{ fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase" }}>{user.role}</div>
            </div>
            <button className="secondary" onClick={handleLogout}>Logout</button>
          </div>
        )}
      </header>

      {errorMsg && (
        <div style={{ padding: "16px", marginBottom: "24px", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: "12px", color: "var(--color-error)", fontSize: "14px" }}>
          <strong>Error:</strong> {errorMsg}
        </div>
      )}

      {successMsg && (
        <div style={{ padding: "16px", marginBottom: "24px", backgroundColor: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.2)", borderRadius: "12px", color: "var(--color-success)", fontSize: "14px" }}>
          <strong>Success:</strong> {successMsg}
        </div>
      )}

      {/* LOGIN PANEL */}
      {view === "login" && (
        <div className="glass-panel" style={{ maxWidth: "450px", margin: "60px auto" }}>
          <h2 style={{ textAlign: "center", marginBottom: "30px" }}>Sign In to eVault</h2>
          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Email Address</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <button type="submit" style={{ marginTop: "10px" }}>Sign In</button>
          </form>

          <p style={{ textAlign: "center", marginTop: "24px", fontSize: "14px", color: "var(--text-secondary)" }}>
            Need an account?{" "}
            <span onClick={() => navigateTo("register")} style={{ color: "var(--color-primary)", cursor: "pointer", textDecoration: "underline" }}>
              Register here
            </span>
          </p>

          <div style={{ marginTop: "32px", paddingTop: "24px", borderTop: "1px solid rgba(255, 255, 255, 0.08)" }}>
            <h4 style={{ margin: "0 0 16px 0", fontSize: "13px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Sandbox Demo Accounts</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <button className="secondary" onClick={() => handleDemoLogin("LAWYER")}>Lead Lawyer</button>
              <button className="secondary" onClick={() => handleDemoLogin("CLIENT")}>Client</button>
              <button className="secondary" onClick={() => handleDemoLogin("JUDGE")}>Presiding Judge</button>
              <button className="secondary" onClick={() => handleDemoLogin("ADMIN")}>System Admin</button>
            </div>
          </div>
        </div>
      )}

      {/* REGISTRATION PANEL */}
      {view === "register" && (
        <div className="glass-panel" style={{ maxWidth: "450px", margin: "60px auto" }}>
          <h2 style={{ textAlign: "center", marginBottom: "30px" }}>Create eVault Profile</h2>
          <form onSubmit={handleRegister} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Email Address</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Password (Min 8 characters)</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Full Name</label>
              <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="LAWYER">LAWYER</option>
                <option value="JUDGE">JUDGE</option>
                <option value="CLIENT">CLIENT</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>
            <button type="submit" style={{ marginTop: "10px" }}>Register Account</button>
          </form>

          <p style={{ textAlign: "center", marginTop: "24px", fontSize: "14px", color: "var(--text-secondary)" }}>
            Already registered?{" "}
            <span onClick={() => navigateTo("login")} style={{ color: "var(--color-primary)", cursor: "pointer", textDecoration: "underline" }}>
              Log in here
            </span>
          </p>
        </div>
      )}

      {/* DASHBOARD VIEW */}
      {view === "dashboard" && user && (
        <div style={{ display: "flex", flexDirection: "column", gap: "30px" }}>
          
          <div className="grid grid-2">
            <div className="glass-panel">
              <h3 style={{ margin: "0 0 16px 0" }}>Create Legal Case</h3>
              {user.role === "LAWYER" ? (
                <form onSubmit={handleCreateCase} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Case Number</label>
                    <input type="text" value={newCaseNumber} placeholder="e.g. CASE-2026-904" onChange={(e) => setNewCaseNumber(e.target.value)} required />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Case Title</label>
                    <input type="text" value={newCaseTitle} placeholder="e.g. Property Dispute Appeal" onChange={(e) => setNewCaseTitle(e.target.value)} required />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Brief Summary</label>
                    <textarea value={newCaseDesc} onChange={(e) => setNewCaseDesc(e.target.value)} style={{ height: "60px" }} />
                  </div>
                  <button type="submit" style={{ alignSelf: "flex-start" }}>Create Case</button>
                </form>
              ) : (
                <p style={{ color: "var(--text-secondary)", fontSize: "14px", margin: 0 }}>
                  Only Lawyer accounts are authorized to register new cases on the ledger.
                </p>
              )}
            </div>

            <div className="glass-panel" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <h3 style={{ margin: "0 0 8px 0" }}>Secure Blockchain Anchoring</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.5" }}>
                  The Legal eVault registry hashes uploaded document revisions, cryptographically signs the record state using keys held strictly on HSM modules, and registers the evidence nodes directly on the Ethereum ledger.
                </p>
              </div>
              <div style={{ background: "rgba(255, 255, 255, 0.02)", padding: "16px", borderRadius: "12px", border: "1px solid var(--border-glass)", fontSize: "13px" }}>
                <span style={{ color: "var(--text-secondary)" }}>Secured Ledger Network:</span> <strong style={{ color: "var(--color-success)" }}>Hardhat Node Active</strong>
              </div>
            </div>
          </div>

          <div className="glass-panel">
            <h3 style={{ margin: "0 0 20px 0" }}>Cases Registered Under Ledger</h3>
            {cases.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>No active case files found for your credentials.</p>
            ) : (
              <table style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ width: "20%" }}>Case Number</th>
                    <th>Title</th>
                    <th style={{ width: "15%" }}>Status</th>
                    <th style={{ width: "15%", textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id}>
                      <td><code style={{ color: "var(--color-neutral)" }}>{c.case_number}</code></td>
                      <td><strong>{c.title}</strong></td>
                      <td>
                        <span className="badge" style={{ background: "rgba(139, 92, 246, 0.15)", color: "var(--color-neutral)" }}>
                          {c.status}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <button onClick={() => fetchCaseDetail(c.id)}>Open Vault</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* CASE DETAIL VIEW */}
      {view === "case_detail" && caseDetail && user && (
        <div style={{ display: "flex", flexDirection: "column", gap: "30px" }}>
          
          <div>
            <button className="secondary" onClick={() => navigateTo("dashboard")}>&lt; Back to Dashboard</button>
          </div>

          <div className="glass-panel">
            <div style={{ borderBottom: "1px solid var(--border-glass)", paddingBottom: "16px", marginBottom: "20px" }}>
              <span style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Ledger Record: {caseDetail.case_number}</span>
              <h2 style={{ margin: "4px 0 0 0" }}>{caseDetail.title}</h2>
            </div>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.6" }}>
              {caseDetail.description || "No case summary description registered."}
            </p>
          </div>

          <div className="grid grid-2">
            
            {/* Left: Participants list */}
            <div className="glass-panel">
              <h3 style={{ margin: "0 0 16px 0" }}>Authorized Case Participants</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "24px" }}>
                {caseDetail.participants.map((p) => (
                  <div key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(255, 255, 255, 0.02)", padding: "12px", borderRadius: "8px", border: "1px solid var(--border-glass)" }}>
                    <div>
                      <div style={{ fontWeight: "600", fontSize: "14px" }}>{p.display_name || "N/A"}</div>
                      <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{p.email}</div>
                    </div>
                    <span className="badge" style={{ background: "rgba(255, 255, 255, 0.05)", border: "1px solid var(--border-glass)" }}>
                      {p.role}
                    </span>
                  </div>
                ))}
              </div>

              {isLead() && (
                <div style={{ borderTop: "1px solid var(--border-glass)", paddingTop: "20px" }}>
                  <h4 style={{ margin: "0 0 12px 0", fontSize: "13px" }}>Authorize New Case Participant</h4>
                  <form onSubmit={handleAddParticipant} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    <input type="text" placeholder="Participant User UUID" value={partUserId} onChange={(e) => setPartUserId(e.target.value)} required />
                    <select value={partRole} onChange={(e) => setPartRole(e.target.value)}>
                      <option value="client">client</option>
                      <option value="opposing_counsel">opposing_counsel</option>
                      <option value="co_counsel">co_counsel</option>
                      <option value="presiding_judge">presiding_judge</option>
                      <option value="lead_lawyer">lead_lawyer</option>
                    </select>
                    <button type="submit">Grant Case Role</button>
                  </form>
                </div>
              )}
            </div>

            {/* Right: Upload document (Lawyer only) */}
            <div className="glass-panel">
              <h3 style={{ margin: "0 0 16px 0" }}>Register Legal Document</h3>
              {user.role === "LAWYER" ? (
                <form onSubmit={handleUploadDocument} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Document Title</label>
                    <input type="text" value={docTitle} onChange={(e) => setDocTitle(e.target.value)} required placeholder="e.g. Signature Land Title Deed" />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Document Type</label>
                    <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                      <option value="pleading">pleading</option>
                      <option value="evidence">evidence</option>
                      <option value="contract">contract</option>
                      <option value="court_order">court_order</option>
                    </select>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>PDF Payload File</label>
                    <input id="doc-file-input" type="file" accept=".pdf" onChange={(e) => setDocFile(e.target.files?.[0] || null)} required />
                  </div>
                  <button type="submit">Upload and Commit to Chain</button>
                </form>
              ) : (
                <p style={{ color: "var(--text-secondary)", fontSize: "14px", margin: 0 }}>
                  Standard Case participants can only view or download authorized records, but cannot commit files.
                </p>
              )}
            </div>

          </div>

          {/* Documents Table */}
          <div className="glass-panel">
            <h3 style={{ margin: "0 0 20px 0" }}>Case Record Index Ledger</h3>
            {documents.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>No document records committed under this case.</p>
            ) : (
              <table style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Classification</th>
                    <th>Uploaded At</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((d) => (
                    <tr key={d.id}>
                      <td><strong>{d.title}</strong></td>
                      <td><code style={{ textTransform: "uppercase", fontSize: "12px" }}>{d.document_type}</code></td>
                      <td><span className="badge" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid var(--border-glass)" }}>{d.classification}</span></td>
                      <td style={{ fontSize: "13px", color: "var(--text-secondary)" }}>{new Date(d.created_at).toLocaleString()}</td>
                      <td style={{ textAlign: "right" }}>
                        <button onClick={() => fetchDocumentPassport(d.id)}>Inspect Passport</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Document Passport Evidence Drawer (Renders below table if selected) */}
          {selectedDoc && (
            <div className="glass-panel" style={{ border: "2px solid var(--color-primary)", boxShadow: "0 0 20px rgba(99, 102, 241, 0.15)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--border-glass)", paddingBottom: "16px", marginBottom: "20px" }}>
                <div>
                  <span style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--color-primary)", fontWeight: "600" }}>Legal Record Evidence Passport</span>
                  <h2 style={{ margin: "4px 0 0 0" }}>{selectedDoc.title}</h2>
                  <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>UUID: {selectedDoc.id}</span>
                </div>
                <button className="secondary" onClick={() => setSelectedDoc(null)}>Close Drawer</button>
              </div>

              {/* Tabs Navigation */}
              <div style={{ display: "flex", gap: "10px", marginBottom: "24px", borderBottom: "1px solid var(--border-glass)", paddingBottom: "10px" }}>
                <button className={docTab === "passport" ? "" : "secondary"} onClick={() => setDocTab("passport")}>Provenance Lineage</button>
                <button className={docTab === "grants" ? "" : "secondary"} onClick={() => setDocTab("grants")}>Access Controls</button>
                <button className={docTab === "audit" ? "" : "secondary"} onClick={() => setDocTab("audit")}>Enforced Audit Trail</button>
                {user.role === "LAWYER" && (
                  <button className={docTab === "new_version" ? "" : "secondary"} onClick={() => setDocTab("new_version")}>Commit Revision</button>
                )}
              </div>

              {/* TABS CONTENT */}
              {/* TAB 1: Passport Flow & Verification Lineage */}
              {docTab === "passport" && (
                <div>
                  <h4 style={{ margin: "0 0 16px 0" }}>Blockchain Registry Lineage Audit</h4>
                  
                  <div className="timeline">
                    {selectedDoc.versions.map((ver) => {
                      const isLatest = ver.id === selectedDoc.current_version_id;
                      const pubVerifyUrl = ver.public_verification_url;
                      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(pubVerifyUrl)}`;

                      return (
                        <div key={ver.id} className="timeline-item">
                          <div className={`timeline-dot ${isLatest ? "active" : ""}`} />
                          <div className="timeline-content">
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px", flexWrap: "wrap", gap: "10px" }}>
                              <div>
                                <span style={{ fontWeight: "700", color: "#fff" }}>Version {ver.version_number}</span>
                                {isLatest && <span className="badge verified" style={{ marginLeft: "8px", fontSize: "10px" }}>Latest Rev</span>}
                                <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
                                  Registered: {new Date(ver.created_at).toLocaleString()}
                                </div>
                              </div>
                              <div style={{ display: "flex", gap: "8px" }}>
                                <button className="secondary" style={{ padding: "4px 10px", fontSize: "12px" }} onClick={() => handleDownloadFile(ver.id, ver.version_number)}>Download File</button>
                              </div>
                            </div>

                            <div className="grid grid-2" style={{ marginTop: "12px" }}>
                              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                                <div style={{ fontSize: "13px" }}>
                                  <span style={{ color: "var(--text-secondary)" }}>Cryptographic SHA-256 Fingerprint:</span>
                                  <div style={{ wordBreak: "break-all", background: "rgba(0,0,0,0.2)", padding: "6px", borderRadius: "6px", border: "1px solid var(--border-glass)", fontSize: "12px", marginTop: "4px", color: "var(--text-secondary)" }}>
                                    {ver.sha256_hash}
                                  </div>
                                </div>

                                <div style={{ fontSize: "13px" }}>
                                  <span style={{ color: "var(--text-secondary)" }}>Blockchain Anchoring Status:</span>
                                  <div style={{ marginTop: "4px", display: "flex", alignItems: "center", gap: "8px" }}>
                                    <span className="badge verified" style={{ fontSize: "10px", background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                                      {ver.blockchain_status}
                                    </span>
                                    {ver.blockchain_block_number && (
                                      <span style={{ color: "var(--text-secondary)", fontSize: "12px" }}>
                                        Block #{ver.blockchain_block_number}
                                      </span>
                                    )}
                                  </div>
                                </div>

                                {ver.blockchain_tx_hash && (
                                  <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                                    Tx Hash: <span style={{ wordBreak: "break-all" }}>{ver.blockchain_tx_hash}</span>
                                  </div>
                                )}
                              </div>

                              {/* QR Code and Independent dropzone */}
                              <div style={{ borderLeft: "1px solid var(--border-glass)", paddingLeft: "20px", display: "flex", gap: "16px", flexWrap: "wrap" }}>
                                <div style={{ textAlign: "center" }}>
                                  <div style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: "6px" }}>Verification Link QR</div>
                                  <img src={qrUrl} alt="QR Code Link" style={{ width: "90px", height: "90px", borderRadius: "8px", border: "4px solid white" }} />
                                  <div style={{ marginTop: "6px" }}>
                                    <a href={pubVerifyUrl} target="_blank" rel="noreferrer" style={{ fontSize: "10px", color: "var(--color-primary)" }}>Open Portal Page</a>
                                  </div>
                                </div>

                                <div style={{ flex: 1 }}>
                                  <div style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: "6px" }}>Verify File Copy</div>
                                  <div 
                                    className="dropzone" 
                                    style={{ padding: "16px 8px", fontSize: "12px" }}
                                    onDragOver={(e) => e.preventDefault()}
                                    onDrop={(e) => {
                                      e.preventDefault();
                                      const file = e.dataTransfer.files?.[0];
                                      if (file) handleVerifyFileLocal(file, ver.opaque_verification_id);
                                    }}
                                    onClick={() => {
                                      const input = document.createElement("input");
                                      input.type = "file";
                                      input.accept = ".pdf";
                                      input.onchange = (e) => {
                                        const file = (e.target as HTMLInputElement).files?.[0];
                                        if (file) handleVerifyFileLocal(file, ver.opaque_verification_id);
                                      };
                                      input.click();
                                    }}
                                  >
                                    Drop file or click to run integrity check
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Verification Results Panel */}
                  {verificationResult && (
                    <div style={{ marginTop: "24px", background: "rgba(255, 255, 255, 0.02)", padding: "20px", borderRadius: "12px", border: "1px solid var(--border-glass)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                        <h4 style={{ margin: 0 }}>Integrity Check Output</h4>
                        <span className={`badge ${
                          verificationResult.status === "VERIFIED" ? "verified" :
                          verificationResult.status === "INTEGRITY_FAILURE" ? "integrity-failure" :
                          verificationResult.status === "VERIFICATION_UNAVAILABLE" ? "unavailable" : "not-found"
                        }`}>
                          {verificationResult.status}
                        </span>
                      </div>
                      <p style={{ fontSize: "14px", color: "var(--text-primary)", margin: "0 0 12px 0" }}>
                        {verificationResult.details}
                      </p>
                      {verificationResult.candidate_hash && (
                        <div style={{ fontSize: "12px", color: "var(--text-secondary)", wordBreak: "break-all" }}>
                          Candidate Hash: <code>{verificationResult.candidate_hash}</code>
                        </div>
                      )}
                      
                      {/* Legal Disclaimer Requirement */}
                      <div style={{ marginTop: "16px", paddingTop: "12px", borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: "11px", color: "var(--text-muted)", lineHeight: "1.4" }}>
                        <strong>Legal Disclaimer:</strong> "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: Access Grants & Permission Settings */}
              {docTab === "grants" && (
                <div>
                  <h4 style={{ margin: "0 0 16px 0" }}>Document Access Management</h4>

                  <div className="grid grid-2" style={{ gap: "24px" }}>
                    <div>
                      <h5 style={{ margin: "0 0 12px 0", color: "var(--text-secondary)" }}>Active Permits</h5>
                      {grants.length === 0 ? (
                        <p style={{ fontSize: "14px", color: "var(--text-secondary)" }}>No active fine-grained access grants exist for this document.</p>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                          {grants.map((g) => (
                            <div key={g.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(255,255,255,0.02)", padding: "12px", border: "1px solid var(--border-glass)", borderRadius: "8px" }}>
                              <div>
                                <div style={{ fontSize: "14px", fontWeight: "600" }}>{g.granted_to_email || g.granted_to_user_id}</div>
                                <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                                  Level: <code style={{ color: "var(--color-success)" }}>{g.permission}</code> | Expires: {g.expires_at ? new Date(g.expires_at).toLocaleString() : "Never"}
                                </div>
                              </div>
                              <button className="danger" style={{ padding: "4px 10px", fontSize: "12px" }} onClick={() => handleRevokeGrant(g.id)}>Revoke</button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Grant new permit form */}
                    <div style={{ background: "rgba(255, 255, 255, 0.01)", padding: "20px", border: "1px solid var(--border-glass)", borderRadius: "12px" }}>
                      <h5 style={{ margin: "0 0 16px 0" }}>Grant New Permit</h5>
                      <form onSubmit={handleGrantAccess} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Grant To Case Participant</label>
                          <select value={grantToUserId} onChange={(e) => setGrantToUserId(e.target.value)} required>
                            <option value="">-- Choose Participant --</option>
                            {caseDetail.participants.map(p => (
                              <option key={p.id} value={p.user_id}>{p.display_name} ({p.role})</option>
                            ))}
                          </select>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Access Scope Permission</label>
                          <select value={grantPermission} onChange={(e) => setGrantPermission(e.target.value as any)}>
                            <option value="VIEW">VIEW</option>
                            <option value="DOWNLOAD">DOWNLOAD</option>
                          </select>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>Duration Limit (Optional Minutes)</label>
                          <input type="number" placeholder="Leave empty for infinite duration" value={grantExpiryMins} onChange={(e) => setGrantExpiryMins(e.target.value)} />
                        </div>
                        <button type="submit">Register Grant</button>
                      </form>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: Enforced Audit Trail */}
              {docTab === "audit" && (
                <div>
                  <h4 style={{ margin: "0 0 16px 0" }}>Database-Enforced Immutable Audit Event Log</h4>
                  <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginBottom: "20px" }}>
                    The log events below are captured by Postgres triggers enforcing append-only immutability. No user, administrator, or service account has permissions to alter these records.
                  </p>
                  
                  {docAudit.length === 0 ? (
                    <p style={{ fontSize: "14px", color: "var(--text-secondary)" }}>No access audit logs exist for this document.</p>
                  ) : (
                    <div style={{ border: "1px solid var(--border-glass)", borderRadius: "12px", overflow: "hidden" }}>
                      <table style={{ margin: 0 }}>
                        <thead>
                          <tr>
                            <th>Timestamp</th>
                            <th>Event Action</th>
                            <th>Actor Type</th>
                            <th>Internal Details</th>
                          </tr>
                        </thead>
                        <tbody>
                          {docAudit.map((evt) => (
                            <tr key={evt.id}>
                              <td style={{ fontSize: "13px", color: "var(--text-secondary)" }}>{new Date(evt.created_at).toLocaleString()}</td>
                              <td><strong style={{ color: evt.event_type.includes("DENIED") ? "var(--color-error)" : "var(--text-primary)" }}>{evt.event_type}</strong></td>
                              <td><code style={{ fontSize: "12px" }}>{evt.actor_type}</code></td>
                              <td style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                                {evt.actor_user_id ? `User: ${evt.actor_user_id}` : "Anonymous portal matches check"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 4: Commit Revision (New Version) */}
              {docTab === "new_version" && (
                <div style={{ maxWidth: "500px" }}>
                  <h4 style={{ margin: "0 0 12px 0" }}>Anchor Document Revision</h4>
                  <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginBottom: "20px" }}>
                    Anchoring a new file copy increments the lineage tree automatically, maintaining strict provenance connection back to the prior version.
                  </p>
                  <form onSubmit={handleUploadVersion} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                      <label style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-secondary)" }}>PDF Revision File</label>
                      <input id="ver-file-input" type="file" accept=".pdf" onChange={(e) => setVerFile(e.target.files?.[0] || null)} required />
                    </div>
                    <button type="submit">Upload and Commit to Chain</button>
                  </form>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* PUBLIC VERIFICATION PORTAL VIEW (UNAUTHENTICATED) */}
      {view === "verify_public" && publicOpaqueId && (
        <div className="glass-panel" style={{ maxWidth: "600px", margin: "40px auto" }}>
          
          <div style={{ textAlign: "center", borderBottom: "1px solid var(--border-glass)", paddingBottom: "24px", marginBottom: "30px" }}>
            <span style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--color-primary)", fontWeight: "600", letterSpacing: "0.15em" }}>Independent Registry matching portal</span>
            <h2 style={{ margin: "6px 0 0 0", fontSize: "28px" }}>Public File Verification</h2>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "6px" }}>
              Target Opaque Ref: <code style={{ color: "var(--color-neutral)" }}>{publicOpaqueId}</code>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.6", textAlign: "center" }}>
              Upload your local copy of the document PDF here. The system will compute its SHA-256 fingerprint locally in your browser sandboxed environment, then matches it against the confirmed cryptographic footprint registered on-chain for this opaque reference ID.
            </p>

            <div 
              className="dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const file = e.dataTransfer.files?.[0];
                if (file) handleVerifyFileLocal(file, publicOpaqueId, true);
              }}
              onClick={() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = ".pdf";
                input.onchange = (e) => {
                  const file = (e.target as HTMLInputElement).files?.[0];
                  if (file) handleVerifyFileLocal(file, publicOpaqueId, true);
                };
                input.click();
              }}
            >
              {verifyingFile ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px", alignItems: "center" }}>
                  <div style={{ width: "24px", height: "24px", border: "3px solid rgba(255,255,255,0.1)", borderTopColor: "var(--color-primary)", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
                  <span>Computing File Signature & Querying Blockchain...</span>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <div style={{ fontSize: "24px" }}>📥</div>
                  <strong>Drop document copy PDF here</strong>
                  <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>or click to browse local folders</span>
                </div>
              )}
            </div>

            {verificationResult && (
              <div style={{ padding: "20px", borderRadius: "12px", border: "1px solid var(--border-glass)", background: "rgba(255, 255, 255, 0.02)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <h4 style={{ margin: 0 }}>Verification Output</h4>
                  <span className={`badge ${
                    verificationResult.status === "VERIFIED" ? "verified" :
                    verificationResult.status === "INTEGRITY_FAILURE" ? "integrity-failure" :
                    verificationResult.status === "VERIFICATION_UNAVAILABLE" ? "unavailable" : "not-found"
                  }`}>
                    {verificationResult.status}
                  </span>
                </div>
                
                <p style={{ margin: "0 0 16px 0", fontSize: "14px", lineHeight: "1.5" }}>
                  {verificationResult.details}
                </p>

                {verificationResult.candidate_hash && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px", fontSize: "12px", color: "var(--text-secondary)", wordBreak: "break-all" }}>
                    <span>Computed Hash (Local File):</span>
                    <code>{verificationResult.candidate_hash}</code>
                  </div>
                )}

                {verificationResult.status === "VERIFIED" && verificationResult.blockchain_timestamp && (
                  <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: "13px", color: "var(--text-secondary)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <span>Blockchain Block:</span>
                      <strong>#{verificationResult.blockchain_block_number}</strong>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <span>Anchor Timestamp:</span>
                      <strong>{new Date(verificationResult.blockchain_timestamp).toLocaleString()}</strong>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "6px" }}>
                      <span>Tx Hash:</span>
                      <code style={{ wordBreak: "break-all", fontSize: "11px", color: "var(--text-muted)" }}>{verificationResult.blockchain_tx_hash}</code>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Legal Disclaimer visible in Public Matching View */}
            <div style={{ background: "rgba(255, 255, 255, 0.01)", padding: "16px", borderRadius: "10px", border: "1px solid var(--border-glass)", fontSize: "12px", color: "var(--text-secondary)", lineHeight: "1.5" }}>
              <strong>Legal Disclaimer:</strong> "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
            </div>

            <div style={{ display: "flex", justifyContent: "center", marginTop: "10px" }}>
              <button className="secondary" onClick={() => navigateTo(token ? "dashboard" : "login")}>
                Go to login area
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Simple style block for spin keyframe animation */}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>

    </div>
  );
}
