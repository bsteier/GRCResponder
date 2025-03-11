import React from "react";
import '../styles/MessageBox.css'
// import {MenuOutlined, EditOutlined} from "@ant-design/icons";

interface MessageBoxProps {
    children: React.ReactNode;
    isUserMessage: boolean;
}

const MessageBox: React.FC<MessageBoxProps> = ({ children, isUserMessage }) => {
  return (
    <div className={`messagebox-container ${isUserMessage ? 'user-message' : 'bot-message'}`}>
        {children}
    </div>
  );
};

export default MessageBox;
