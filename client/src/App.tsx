import React, { useState } from 'react';
import './styles/App.css';
import Home from './pages/Home';
import PdfViewer from 'components/PDFViewer';
import { Routes, Route } from 'react-router-dom';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/viewer/:fileName" element={<PdfViewer />} />
    </Routes>
  );
}

export default App;