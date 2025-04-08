import React, { useEffect, useRef, useState } from "react";
import { getDocument, PDFDocumentProxy } from "pdfjs-dist";

const PdfViewer: React.FC = () => {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const pdfPath = "/Hw2.pdf"; // should be in public folder

  useEffect(() => {
    const loadPdf = async () => {
      const loadingTask = getDocument(pdfPath);
      const doc = await loadingTask.promise;
      setPdf(doc);
      setNumPages(doc.numPages);
    };

    loadPdf();
  }, []);

    useEffect(() => {
        let renderTask: any; // Allows us to refresh the page (without it we get a canvas render error)
        const renderPage = async () => {
        if (!pdf) return;
    
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.5 });
        const canvas = canvasRef.current;
        if (!canvas) return;
    
        const context = canvas.getContext("2d");
        canvas.height = viewport.height;
        canvas.width = viewport.width;
    
        const renderContext = {
            canvasContext: context!,
            viewport,
        };
    
        renderTask = page.render(renderContext);
        try {
            await renderTask.promise;
        } catch (error) {
            if (error?.name !== "RenderingCancelledException") {
            console.error("Render failed:", error);
            }
        }
        };
    
        renderPage();
    
        return () => {
        if (renderTask) {
            renderTask.cancel();
        }
        };
    }, [pdf, pageNumber]);
  

  const goToPrevPage = () => setPageNumber((prev) => Math.max(prev - 1, 1));
  const goToNextPage = () => setPageNumber((prev) => Math.min(prev + 1, numPages));

  return (
    <div className="p-4">
      <h1 className="text-xl font-bold mb-4">PDF Viewer</h1>

      <div className="mb-4 flex items-center gap-4">
        <button onClick={goToPrevPage} disabled={pageNumber === 1} className="px-3 py-1 bg-gray-200 rounded">
          Previous
        </button>
        <span>
          Page {pageNumber} of {numPages}
        </span>
        <button onClick={goToNextPage} disabled={pageNumber === numPages} className="px-3 py-1 bg-gray-200 rounded">
          Next
        </button>
      </div>

      <canvas ref={canvasRef} className="border shadow rounded" />
    </div>
  );
};

export default PdfViewer;
