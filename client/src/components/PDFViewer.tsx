import { Worker, Viewer } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';

import { useNavigate } from 'react-router-dom';

const PdfViewer = () => {
  const navigate = useNavigate();
  const defaultLayoutPluginInstance = defaultLayoutPlugin();

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Back Button */}
      <div style={{ padding: '10px' }}>
        <button
          onClick={() => navigate(-1)}
          style={{
            padding: '8px 12px',
            backgroundColor: '#f0f0f0',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          ← Back to Chat
        </button>
      </div>

      {/* PDF Viewer */}
      <div style={{ flex: 1, height: 0 }}>
        <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
          <Viewer
            fileUrl="/Hw2.pdf"
            plugins={[defaultLayoutPluginInstance]}
          />
        </Worker>
      </div>
    </div>
  );
};

export default PdfViewer;
