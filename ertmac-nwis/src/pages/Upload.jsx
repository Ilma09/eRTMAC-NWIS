import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  X,
  CheckCircle2,
  FileArchive,
  FolderOpen,
  AlertTriangle,
  ArrowUpRight,
} from "lucide-react";

import api from "../api/client";

import "./Upload.css";

function Upload() {
  const [uploadType, setUploadType] = useState("WCR");
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);

  const fileInputRef = useRef(null);

  /* Only WCR/DDR, PDF-only - matches the backend exactly (POST /api/upload
     accepts doc_type WCR or DDR and rejects anything but a .pdf regardless
     of category). A CSV/Excel "Well Data" category used to be offered here
     but there's no backend ingestion path for it at all - it would always
     fail, so it's not offered rather than left as a guaranteed dead end. */
  const uploadOptions = [
    {
      id: "WCR",
      title: "Well Completion Report",
      short: "WCR",
      icon: FileText,
      description: "Well construction & completion records",
      accept: ".pdf",
      types: [".pdf"],
    },
    {
      id: "DDR",
      title: "Daily Drilling Report",
      short: "DDR",
      icon: FileSpreadsheet,
      description: "Daily drilling & operational records",
      accept: ".pdf",
      types: [".pdf"],
    },
  ];

  const selectedType = uploadOptions.find(
    (item) => item.id === uploadType
  );

  const SelectedIcon = selectedType.icon;

  const handleFile = (selectedFile) => {
    if (!selectedFile) return;

    const extension =
      "." + selectedFile.name.split(".").pop().toLowerCase();

    if (!selectedType.types.includes(extension)) {
      alert(
        `Invalid file type.\n\n${selectedType.title} supports:\n${selectedType.types.join(
          ", "
        )}`
      );
      return;
    }

    setFile(selectedFile);
    setResult(null);
  };

  const handleFileChange = (event) => {
    handleFile(event.target.files[0]);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);

    const droppedFile = event.dataTransfer.files[0];

    handleFile(droppedFile);
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = () => {
    setDragActive(false);
  };

  const changeUploadType = (type) => {
    setUploadType(type);
    setFile(null);
    setResult(null);
  };

  const removeFile = () => {
    setFile(null);
    setResult(null);
  };

  const handleUpload = async () => {
    if (!file) {
      alert("Please select a file first.");
      return;
    }

    setUploading(true);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_type", uploadType);

    try {
      // Don't set a Content-Type header here - axios/the browser fill in
      // the multipart boundary automatically for a FormData body, and a
      // manual "multipart/form-data" header without one breaks parsing.
      const res = await api.post("/api/upload", formData);

      if (res.data.status === "REJECTED_DUPLICATE") {
        setResult({
          status: "duplicate",
          message:
            res.data.message ||
            "This document has already been uploaded.",
        });
      } else {
        setResult({
          status: "success",
          documentId: res.data.document_id,
        });
      }

      setFile(null);
    } catch (err) {
      setResult({
        status: "error",
        message:
          err.response?.data?.detail ||
          "Upload failed. Is the backend running?",
      });
    } finally {
      setUploading(false);
    }
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;

    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="upload-page">

      {/* =================================================
          PAGE HEADER
      ================================================= */}

      <div className="upload-header">

        <div>

          <span className="upload-eyebrow">
            eRTMAC-NWIS / DATA MANAGEMENT
          </span>

          <h1>
            Upload Data
          </h1>

          <p>
            Import well reports, drilling records,
            documents and spatial datasets into the
            Nearby Wells Intelligence System.
          </p>

        </div>

        <div className="repository-status">

          <span className="online-dot"></span>

          <div>
            <strong>Repository Online</strong>
            <small>Ready to receive data</small>
          </div>

        </div>

      </div>


      {/* =================================================
          UPLOAD TYPE
      ================================================= */}

      <div className="upload-section">

        <div className="upload-section-header">

          <div>

            <span>DATA CATEGORY</span>

            <h2>
              Select what you want to upload
            </h2>

          </div>

          <small>
            Choose one category
          </small>

        </div>


        <div className="upload-category-grid">

          {uploadOptions.map((item) => {

            const Icon = item.icon;

            const active =
              uploadType === item.id;

            return (
              <button
                key={item.id}
                className={`upload-category ${
                  active ? "active" : ""
                }`}
                onClick={() =>
                  changeUploadType(item.id)
                }
              >

                <div className="category-icon">
                  <Icon size={20} />
                </div>

                <div className="category-text">

                  <strong>
                    {item.short}
                  </strong>

                  <span>
                    {item.title}
                  </span>

                </div>

                {active && (
                  <CheckCircle2
                    size={17}
                    className="category-check"
                  />
                )}

              </button>
            );
          })}

        </div>

      </div>


      {/* =================================================
          MAIN UPLOAD AREA
      ================================================= */}

      <div className="upload-main-card">

        {/* LEFT SIDE */}

        <div className="upload-info-panel">

          <div className="current-upload-icon">
            <SelectedIcon size={28} />
          </div>

          <span className="current-label">
            SELECTED DATA TYPE
          </span>

          <h2>
            {selectedType.title}
          </h2>

          <p>
            {selectedType.description}.
            Upload your file using the area on the right.
          </p>


          <div className="upload-details">

            <div>

              <span>Accepted formats</span>

              <strong>
                {selectedType.types.join(", ")}
              </strong>

            </div>

            <div>

              <span>Processing</span>

              <strong>
                Data Validation
              </strong>

            </div>

          </div>

        </div>


        {/* RIGHT SIDE */}

        <div className="upload-drop-panel">

          <div
            className={`upload-drop-zone ${
              dragActive ? "drag-active" : ""
            }`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >

            <div className="upload-cloud">

              <UploadCloud size={34} />

            </div>

            <h3>
              Drag & Drop file here
            </h3>

            <p>
              or select a file from your device
            </p>


            <button
              className="browse-button"
              onClick={() =>
                fileInputRef.current?.click()
              }
            >

              <FolderOpen size={16} />

              Browse Files

            </button>


            <input
              ref={fileInputRef}
              type="file"
              hidden
              accept={selectedType.accept}
              onChange={handleFileChange}
            />


            <span className="drop-hint">

              Supported:
              {" "}
              {selectedType.types.join(" • ")}

            </span>

          </div>


          {/* SELECTED FILE */}

          {file && (

            <div className="selected-file-card">

              <div className="selected-file-left">

                <div className="selected-file-icon">

                  {file.name
                    .toLowerCase()
                    .endsWith(".zip") ? (
                    <FileArchive size={21} />
                  ) : (
                    <FileText size={21} />
                  )}

                </div>


                <div className="selected-file-details">

                  <strong>
                    {file.name}
                  </strong>

                  <span>
                    {formatSize(file.size)}
                    {" • "}
                    {selectedType.short}
                  </span>

                </div>

              </div>


              <button
                className="remove-file"
                onClick={removeFile}
              >

                <X size={17} />

              </button>

            </div>

          )}


          {/* UPLOAD BUTTON */}

          <button
            className="final-upload-button"
            disabled={!file || uploading}
            onClick={handleUpload}
          >

            {uploading ? (
              <>
                <span className="upload-loader"></span>
                Processing...
              </>
            ) : (
              <>
                <UploadCloud size={17} />
                Upload {selectedType.short}
              </>
            )}

          </button>


          {/* UPLOAD RESULT */}

          {result && (

            <div className={`upload-result upload-result-${result.status}`}>

              {result.status === "success" && (
                <>
                  <CheckCircle2 size={17} />
                  <div>
                    <strong>Uploaded successfully</strong>
                    <span>
                      Document #{result.documentId} is now processing.
                      {" "}
                      <Link to="/corpus">
                        View in Corpus <ArrowUpRight size={11} />
                      </Link>
                    </span>
                  </div>
                </>
              )}

              {result.status === "duplicate" && (
                <>
                  <AlertTriangle size={17} />
                  <div>
                    <strong>Already uploaded</strong>
                    <span>{result.message}</span>
                  </div>
                </>
              )}

              {result.status === "error" && (
                <>
                  <AlertTriangle size={17} />
                  <div>
                    <strong>Upload failed</strong>
                    <span>{result.message}</span>
                  </div>
                </>
              )}

            </div>

          )}

        </div>

      </div>


      {/* =================================================
          DOCUMENT INFORMATION
      ================================================= */}

      <div className="upload-bottom">

        <div className="bottom-title">

          <div>

            <span>DOCUMENT INTELLIGENCE</span>

            <h2>
              Supported eRTMAC-NWIS Records
            </h2>

          </div>

        </div>


        <div className="record-grid">

          <div className="record-card">

            <div className="record-icon blue">
              <FileText size={20} />
            </div>

            <div>
              <strong>WCR</strong>

              <span>
                Well Completion Reports
              </span>

              <p>
                Well construction, completion,
                lithology and aquifer information.
              </p>
            </div>

          </div>


          <div className="record-card">

            <div className="record-icon orange">
              <FileSpreadsheet size={20} />
            </div>

            <div>
              <strong>DDR</strong>

              <span>
                Daily Drilling Reports
              </span>

              <p>
                Daily drilling progress,
                activities and operational records.
              </p>
            </div>

          </div>


        </div>

      </div>


    </div>
  );
}

export default Upload;