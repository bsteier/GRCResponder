import React, { useState } from "react";
import '../styles/MessageBox.css'
// import {MenuOutlined, EditOutlined} from "@ant-design/icons";
import {FileOutlined} from "@ant-design/icons"

import { Link } from 'react-router-dom';

interface MessageBoxProps {
    children: React.ReactNode;
    isUserMessage: boolean;
    files?: (File | string)[]; // Array of URLs
}

const MessageBox: React.FC<MessageBoxProps> = ({ children, isUserMessage, files }) => {
  return (
    <div className={`messagebox-container ${isUserMessage ? 'user-message' : 'bot-message'}`}>
      <div dangerouslySetInnerHTML={{ __html: children as string }} /> {/*Forces ts to think this is a string*/}
        {files && (
          <div className="messagebox-files">
            {files.map((file, index) => (
              <Link
                key={`Document-${index}`}
                to={`/viewer${file}`}
                className="messagebox-file inline-flex items-center gap-1"
              >
                {`Document${index + 1}.pdf`} <FileOutlined />
              </Link>
            ))}
          </div>
        )}
    </div>
  );
};

export default MessageBox;