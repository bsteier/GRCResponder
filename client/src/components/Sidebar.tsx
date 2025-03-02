import React from "react";
import '../styles/Sidebar.css'
import {MenuOutlined} from "@ant-design/icons";

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, toggleSidebar }) => {
  return (
    <div className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
            <MenuOutlined className="menu-icon" onClick={toggleSidebar}/>
        </div>
        <div className="sidebar-content">

        </div>
    </div>

  );
};

export default Sidebar;
