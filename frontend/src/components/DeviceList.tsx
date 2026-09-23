import React from 'react';
import { DeviceInfo } from '../types';

interface DeviceListProps {
  devices: DeviceInfo[];
  onDeviceClick?: (device: DeviceInfo) => void;
  onScanClick?: (device: DeviceInfo) => void;
}

export default function DeviceList({ devices, onDeviceClick, onScanClick }: DeviceListProps) {
  if (!devices || devices.length === 0) {
    return (
      <div className="device-list-empty">
        <p>ไม่พบข้อมูลอุปกรณ์</p>
      </div>
    );
  }

  return (
    <div className="device-grid">
      {devices.map((device) => (
        <div 
          key={device.device_id} 
          className="device-card"
          onClick={() => onDeviceClick?.(device)}
        >
          <div className="device-icon">
            {/* ตัวย่อข้อความแทนอิโมจิ — แสดงผลเหมือนกันทุกเครื่อง */}
            {device.device_type === 'projector' ? 'PRJ' :
             device.device_type === 'ac' ? 'AC' :
             device.device_type === 'computer' ? 'PC' : 'DEV'}
          </div>
          <div className="device-info">
            <div className="device-name">{device.device_type}</div>
            <div className="device-room">{device.room_name || 'ไม่ระบุห้อง'}</div>
            <div className="device-status">
              <span className={`status-badge ${device.status || 'unknown'}`}>
                {device.status || 'ไม่ระบุ'}
              </span>
            </div>
          </div>
          <button 
            className="scan-btn"
            onClick={(e) => { e.stopPropagation(); onScanClick?.(device); }}
          >
            สแกน QR
          </button>
        </div>
      ))}
    </div>
  );
}
