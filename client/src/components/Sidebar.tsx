import React, { useState } from "react";
import '../styles/Sidebar.css'
import {MenuOutlined, EditOutlined, MoreOutlined} from "@ant-design/icons";
import { Dropdown, Menu } from "antd";

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
  newChat: () => void;
  loadMessages: (conversationId: string) => void;
  conversationHistory: Array<{ id: string; title: string; timestamp: string }>;
  activeConversationId: string | null;
  onRenameConversation: (id: string, newTitle: string) => void;
  onDeleteConversation: (id: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, toggleSidebar, newChat, loadMessages, conversationHistory, activeConversationId, onRenameConversation, onDeleteConversation }) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const getMenuItems = (id: string, title: string) => ({
    items: [
      {
        key: 'rename',
        label: 'Rename',
        onClick: () => {
          const newTitle = prompt('Rename conversation:', title);
          if (newTitle && newTitle.trim() !== '') {
            onRenameConversation(id, newTitle.trim());
          }
        }
      },
      {
        key: 'delete',
        label: 'Delete',
        onClick: () => {
          if (window.confirm(`Are you sure you want to delete "${title}"?`)) {
            onDeleteConversation(id);
          }
        }
      }
    ]
  });

  return (
    <div className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
            <MenuOutlined className="sidebar-icon" onClick={toggleSidebar}/>
            <EditOutlined className="sidebar-icon" onClick={newChat}/>
        </div>
        <div className={`sidebar-content ${isOpen ? "" : "hidden"}`}>
          <div className='past-chats'>
            <span className='time-title'>Recent</span>
            {conversationHistory.map(convo => (
            <div
              onMouseEnter={() => setHoveredId(convo.id)}
              onMouseLeave={() => setHoveredId(null)}
              className={`chat-title ${activeConversationId === convo.id ? 'active' : ''}`}
            >
              <div
                key={convo.id}
                // className={`chat-title ${activeConversationId === convo.id ? 'active' : ''}`}
                onClick={() => loadMessages(convo.id)}
              >
                <span>{convo.title}</span>
                <span className='chat-time'>{new Date(convo.timestamp).toLocaleDateString()}</span>
              </div>
              {hoveredId === convo.id && (
                  <Dropdown menu={getMenuItems(convo.id, convo.title)} trigger={['click']}>
                    <MoreOutlined className="more-icon" />
                  </Dropdown>
                )}
              </div>
            ))}
          </div>
        </div>
    </div>
    // <div className={`fixed top-0 left-0 h-full bg-gray-800 text-white w-64 transition-transform ${isOpen ? "translate-x-0" : "-translate-x-64"} duration-300`}>
    //   <button className="p-4 text-xl" onClick={toggleSidebar}>✖</button>
    //   <nav className="flex flex-col p-4 space-y-2">
    //     {/* <Link to="/" className="p-2 hover:bg-gray-700 rounded">Home</Link>
    //     <Link to="/about" className="p-2 hover:bg-gray-700 rounded">About</Link>
    //     <Link to="/contact" className="p-2 hover:bg-gray-700 rounded">Contact</Link> */}
    //   </nav>
    // </div>
  );
};

export default Sidebar;
