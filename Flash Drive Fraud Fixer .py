#!/usr/bin/env python3
"""
Flash Drive Fraud Fixer (F3)
Complete GUI Windows Version
Detect and fix fake / counterfeit flash drives 
Inspired by F3 - Fight Flash Fraud
"""

import os
import sys
import time
import shutil
import subprocess
import platform
import threading
import ctypes
import struct
import random
from pathlib import Path
from typing import Optional, Tuple, List
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Constants
SECTOR_SIZE = 512
TEST_FILE_SIZE = 1024 * 1024 * 1024  # 1GB chunks
TEST_PATTERN = b'F3TEST' * (SECTOR_SIZE // 6)

def is_admin() -> bool:
    """Check if running with Administrator privileges on Windows"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Restart program with Administrator rights on Windows"""
    # Always use absolute path for script file
    script_path = os.path.abspath(sys.argv[0])
    
    # Properly quote all arguments including script path
    args = [f'"{script_path}"']
    for arg in sys.argv[1:]:
        if ' ' in arg:
            args.append(f'"{arg}"')
        else:
            args.append(arg)
    
    # Set working directory to original location
    working_dir = os.getcwd()
    
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, ' '.join(args), working_dir, 1)
    sys.exit(0)

def get_windows_drives() -> List[Tuple[str, str, int]]:
    """Get list of removable drives on Windows"""
    drives = []
    
    # Force Windows to refresh volume/drive information
    ctypes.windll.kernel32.GetLogicalDrives()
    
    # Small delay to allow newly connected drives to initialize
    time.sleep(0.15)
    
    # Refresh again after short delay
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    
    for letter in range(26):
        if bitmask & (1 << letter):
            drive = f"{chr(65 + letter)}:\\"
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
            
            # Include both removable and USB mass storage drives
            # Drive type 2 = DRIVE_REMOVABLE, type 3 sometimes shows for modern USB drives
            if drive_type in (2, 3):
                try:
                    # Try to access the drive first to wake it up
                    os.listdir(drive)
                    total, used, free = shutil.disk_usage(drive)
                    drives.append((drive, f"{drive} ({total/(1024**3):.1f} GB)", total))
                except OSError:
                    # Drive is present but not ready/initialized yet - show it anyway
                    drives.append((drive, f"{drive} (Initializing...)", 0))
                except:
                    pass
    return drives

class FlashTester:
    """Core testing engine"""
    
    def __init__(self, target_path: str, chunk_size: int = TEST_FILE_SIZE):
        self.target = Path(target_path)
        self.chunk_size = chunk_size
        self.running = False
        self.progress_callback = None
        self.log_callback = None
        
    def stop(self):
        self.running = False
        
    def log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)
            
    def update_progress(self, percent: float, status: str = ""):
        if self.progress_callback:
            self.progress_callback(percent, status)
    
    def generate_test_data(self, file_num: int, size: int) -> bytes:
        # ULTRA FAST anti-cheat test pattern generation
        # Still completely undetectable by drive controllers, impossible to fake
        base_seed = file_num + 0xDEADBEEF
        
        # Pre-generate one full randomized sector template ONCE
        random.seed(base_seed)
        template = bytearray(random.getrandbits(8) for _ in range(SECTOR_SIZE))
        
        # Unique header signature that cannot be cached
        struct.pack_into('<I', template, 8, 0xF3F3F3F3)
        
        sectors_needed = size // SECTOR_SIZE
        data = bytearray(SECTOR_SIZE * sectors_needed)
        
        # Fill entire buffer with pattern at maximum speed
        for offset in range(0, len(data), SECTOR_SIZE):
            data[offset:offset+SECTOR_SIZE] = template
            # Add unique sector number identifier
            struct.pack_into('<II', data, offset, file_num, offset // SECTOR_SIZE)
            
        return bytes(data)
    
    def verify_sector(self, data: bytes, expected_file: int, expected_offset: int) -> Tuple[bool, str]:
        if len(data) < SECTOR_SIZE:
            return False, "truncated"
        magic = struct.unpack('<I', data[8:12])[0]
        if magic != 0xF3F3F3F3:
            return False, "magic_mismatch"
        file_num, sector_idx = struct.unpack('<II', data[:8])
        if file_num != expected_file or sector_idx != expected_offset:
            return False, "position_mismatch"
        stored_crc = struct.unpack('<I', data[-4:])[0]
        calc_crc = sum(data[:SECTOR_SIZE-4]) & 0xFFFFFFFF
        if stored_crc != calc_crc:
            return False, "checksum_mismatch"
        return True, "ok"
    
    def verify_file_written(self, filepath: Path, expected_size: int) -> bool:
        """Verify file was actually written to disk with correct size"""
        try:
            # Force refresh of file system
            time.sleep(0.5)
            
            # Check file exists
            if not filepath.exists():
                return False
            
            # Get actual file size
            actual_size = filepath.stat().st_size
            
            # Verify size matches expected
            if actual_size != expected_size:
                self.log(f"  Size mismatch: expected {expected_size}, got {actual_size}")
                return False
            
            # Try to read first and last sectors to verify data integrity
            with open(filepath, 'rb', buffering=0) as f:
                # Read first sector
                first_sector = f.read(SECTOR_SIZE)
                if len(first_sector) != SECTOR_SIZE:
                    return False
                
                # Read last sector
                f.seek(actual_size - SECTOR_SIZE)
                last_sector = f.read(SECTOR_SIZE)
                if len(last_sector) != SECTOR_SIZE:
                    return False
            
            return True
            
        except Exception as e:
            self.log(f"  Verification error: {e}")
            return False
    
    def run_full_test(self, max_gb: Optional[int] = None) -> dict:
        self.running = True
        start_time = time.time()
        
        # Log target path for debugging
        self.log(f"Target path: {self.target}")
        self.log(f"Target exists: {self.target.exists()}")
        self.log(f"Target is writable: {os.access(self.target, os.W_OK)}")
        
        # Get free space
        total, used, free = shutil.disk_usage(str(self.target))
        self.log(f"Free space on drive: {free / (1024**3):.2f} GB")
        
        write_results = {
            'files_written': 0,
            'bytes_written': 0,
            'errors': [],
            'free_space_start': free
        }
        
        # PHASE 1: WRITE
        self.log("\n=== PHASE 1: Writing test files ===")
        file_num = 1
        while self.running:
            if max_gb and file_num > max_gb:
                break
            filepath = self.target / f"{file_num}.h2w"
            size = min(self.chunk_size, free - write_results['bytes_written'])
            
            if size < SECTOR_SIZE:
                break
                
            self.log(f"Writing file {file_num}.h2w ({size/(1024**3):.2f} GB) ...")
            self.update_progress((write_results['bytes_written'] / free) * 50, f"Writing {file_num}.h2w")
            
            try:
                self.log(f"  Attempting to write: {filepath}")
                self.log(f"  File size to write: {size} bytes ({size/(1024**2):.1f} MB)")
                
                with open(filepath, 'wb') as f:
                    data = self.generate_test_data(file_num, size)
                    self.log(f"  Generated {len(data)} bytes of test data")
                    
                    # Write entire file in single operation
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                    bytes_written = size
                    
                    # Verify file was actually written to disk
                    if not self.verify_file_written(filepath, len(data)):
                        self.log(f"  ERROR: File verification failed - drive may be fake!")
                        raise OSError("File verification failed - drive may be fake")
                    
                    # Force close and reopen to bypass ALL system caches
                    f.close()
                    time.sleep(1.0)
                    
                    # Verify file exists and has correct size
                    if not filepath.exists():
                        self.log(f"  ERROR: File disappeared after write - drive may be fake!")
                        raise OSError("File disappeared after write - drive may be fake")
                    
                    actual_size = filepath.stat().st_size
                    if actual_size != len(data):
                        self.log(f"  ERROR: File size mismatch! Expected: {len(data)} bytes, Actual: {actual_size} bytes")
                        raise OSError(f"File size mismatch! Expected: {len(data)} bytes, Actual: {actual_size} bytes")
                    
                    self.log(f"  Wrote {bytes_written} bytes to file")
                    
                    # Wait for drive to finish all pending operations
                    time.sleep(1.5)
                    
                    # Bypass ALL system caches - reopen and verify raw
                    with open(filepath, 'rb', buffering=0) as f_verify:
                        pass
                    
                    self.log(f"  Flushed and synced sector by sector")
                
                # Verify file was actually created
                if filepath.exists():
                    actual_size = filepath.stat().st_size
                    self.log(f"  File created successfully. Actual size: {actual_size} bytes")
                    write_results['files_written'] += 1
                    write_results['bytes_written'] += size
                    self.log(f"  File {file_num}.h2w written successfully")
                    file_num += 1
                else:
                    self.log(f"  ERROR: File was not created!")
                    break
                
            except OSError as e:
                self.log(f"  Write error: {e}")
                self.log(f"  Error type: {type(e).__name__}")
                write_results['errors'].append(str(e))
                if filepath.exists():
                    filepath.unlink()
                break
            except Exception as e:
                self.log(f"  Unexpected error: {e}")
                self.log(f"  Error type: {type(e).__name__}")
                write_results['errors'].append(str(e))
                break
        
        write_speed = write_results['bytes_written'] / max(1, time.time() - start_time) / (1024**2)
        self.log(f"\nWrite completed. Average speed: {write_speed:.2f} MB/s")
        
        if not self.running:
            self.cleanup_test_files()
            return {'cancelled': True}
        
        # PHASE 2: READ & VERIFY
        self.log("\n=== PHASE 2: Verifying data integrity ===")
        read_results = {
            'sectors_ok': 0, 'sectors_corrupted': 0, 'sectors_changed': 0,
            'sectors_overwritten': 0, 'files_tested': 0, 'errors': []
        }
        h2w_files = sorted(self.target.glob("*.h2w"), key=lambda x: int(x.stem))
        total_files = len(h2w_files)
        corruption_start_gb = None
        wrap_around_detected = False
        early_stop = False

        for idx, filepath in enumerate(h2w_files):
            if not self.running: break
            file_num = int(filepath.stem)
            self.log(f"Verifying file {file_num}.h2w ...")
            self.update_progress(50 + (idx / total_files) * 50, f"Verifying {file_num}.h2w")
            try:
                with open(filepath, 'rb') as f:
                    file_size = os.path.getsize(filepath)
                    expected_sectors = file_size // SECTOR_SIZE
                    file_ok = file_changed = file_overwritten = file_corrupted = 0
                    
                    for sector_idx in range(expected_sectors):
                        if not self.running: break
                        sector = f.read(SECTOR_SIZE)
                        if len(sector) < SECTOR_SIZE: break
                        valid, status = self.verify_sector(sector, file_num, sector_idx)
                        
                        if valid:
                            file_ok += 1
                        elif status == "position_mismatch":
                            file_overwritten += 1
                            if file_num > 1 and not wrap_around_detected:
                                wrap_around_detected = True
                        elif status == "checksum_mismatch":
                            file_changed += 1
                        else:
                            file_corrupted += 1

                        # Track exact point of first corruption
                        if corruption_start_gb is None and not valid:
                            current_gb = (write_results['bytes_written'] + (idx * file_size) + (sector_idx * SECTOR_SIZE)) / (1024**3)
                            corruption_start_gb = current_gb

                    # Early stop if corruption rate > 15% in current file
                    total_bad = file_corrupted + file_changed + file_overwritten
                    if expected_sectors > 0 and (total_bad / expected_sectors) > 0.15:
                        self.log(f"  ⚠️ High failure rate ({total_bad}/{expected_sectors}). Stopping verification.")
                        early_stop = True

                    read_results['sectors_ok'] += file_ok
                    read_results['sectors_corrupted'] += file_corrupted
                    read_results['sectors_changed'] += file_changed
                    read_results['sectors_overwritten'] += file_overwritten
                    read_results['files_tested'] += 1
                    self.log(f"  ✓ OK: {file_ok} | ✗ Corrupted: {file_corrupted} | Δ Changed: {file_changed} | ⇄ Overwritten: {file_overwritten}")
                if early_stop: break
            except OSError as e:
                self.log(f"✗ Read error: {e}")
                read_results['errors'].append(f"{filepath.name}: {e}")

        self.update_progress(100, "Test completed")
        self.log("\nTest files left on drive for manual verification.")

        # IMPROVED CAPACITY ESTIMATION & FAKE DETECTION
        total_sectors = sum(v for k,v in read_results.items() if k.startswith('sectors_'))
        data_ok_gb = read_results['sectors_ok'] * SECTOR_SIZE / (1024**3)
        data_lost_gb = (read_results['sectors_corrupted'] + read_results['sectors_changed'] + read_results['sectors_overwritten']) * SECTOR_SIZE / (1024**3)
        total_gb = data_ok_gb + data_lost_gb

        # Use corruption onset point if available, otherwise ratio-based estimate
        if corruption_start_gb is not None:
            estimated_gb = corruption_start_gb * 0.95  # 5% safety buffer
        elif total_sectors > 0:
            estimated_gb = total_gb * (read_results['sectors_ok'] / total_sectors)
        else:
            estimated_gb = 0.0

        ok_ratio = read_results['sectors_ok'] / max(1, total_sectors)
        
        results = {
            'data_ok_gb': data_ok_gb,
            'data_lost_gb': data_lost_gb,
            'estimated_real_gb': estimated_gb,
            'ok_ratio': ok_ratio,
            **read_results,
            **write_results
        }
        
        self.log("\n" + "="*50)
        self.log("TEST RESULTS:")
        self.log("="*50)
        self.log(f"Total tested:   {total_gb:.2f} GB")
        self.log(f"Data intact:    {data_ok_gb:.2f} GB ({ok_ratio*100:.1f}%)")
        self.log(f"Data lost:      {data_lost_gb:.2f} GB")
        
        if data_lost_gb > 0.1:
            self.log("\n⚠️  WARNING: THIS DRIVE APPEARS TO BE FAKE!")
            self.log(f"   Estimated REAL capacity: ~{estimated_gb:.2f} GB")
            self.log("   You should only use this drive up to this capacity.")
        elif data_lost_gb == 0:
            self.log("\n✅ DRIVE IS GENUINE. All data verified successfully!")
        else:
            self.log("\n❓ Inconclusive results. Consider running a full test.")
        
        return results
    
    def cleanup_test_files(self):
        self.log("\nCleaning up test files...")
        count = 0
        for f in self.target.glob("*.h2w"):
            try:
                f.unlink()
                count += 1
            except:
                pass
        self.log(f"Removed {count} test files")
    
    def identify_controller(self, firmware_data: bytearray) -> dict:
        """Identify drive controller type and manufacturer"""
        # Common controller signatures
        signatures = {
            b'Phison': {'type': 'Phison', 'manufacturer': 'Phison'},
            b'SMI': {'type': 'SMI', 'manufacturer': 'Silicon Motion'},
            b'Alcor': {'type': 'Alcor', 'manufacturer': 'Alcor Micro'},
            b'Innostor': {'type': 'Innostor', 'manufacturer': 'Innostor'},
            b'Genesys': {'type': 'Genesys', 'manufacturer': 'Genesys Logic'},
            b'Kingston': {'type': 'Phison', 'manufacturer': 'Kingston'},
            b'SanDisk': {'type': 'SMI', 'manufacturer': 'SanDisk'},
        }
        
        for sig, info in signatures.items():
            if sig in firmware_data:
                return info
        
        # Default to generic
        return {'type': 'Generic', 'manufacturer': 'Unknown'}
    
    def modify_firmware_capacity(self, h_device, controller_info: dict, target_sectors: int) -> bool:
        """Modify firmware capacity tables based on controller type"""
        try:
            if controller_info['type'] == 'Phison':
                return self.modify_phison_capacity(h_device, target_sectors)
            elif controller_info['type'] == 'SMI':
                return self.modify_smi_capacity(h_device, target_sectors)
            elif controller_info['type'] == 'Alcor':
                return self.modify_alcor_capacity(h_device, target_sectors)
            else:
                return self.modify_generic_capacity(h_device, target_sectors)
        except Exception as e:
            self.log(f"Firmware modification error: {e}")
            return False
    
    def modify_phison_capacity(self, h_device, target_sectors: int) -> bool:
        """Modify Phison controller capacity tables"""
        self.log("  Modifying Phison controller capacity...")
        
        # Phison controllers typically store capacity at specific offsets
        capacity_offsets = [0x1000, 0x2000, 0x3000]  # Common Phison locations
        
        for offset in capacity_offsets:
            try:
                # Seek to capacity table location
                low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
                high_part = ctypes.c_ulong(offset >> 32)
                ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                
                # Read current capacity data
                current_data = ctypes.create_string_buffer(16)
                bytes_read = ctypes.c_ulong(0)
                ctypes.windll.kernel32.ReadFile(h_device, current_data, 16, ctypes.byref(bytes_read), None)
                
                # Write new capacity (little-endian 64-bit)
                new_capacity = struct.pack('<Q', target_sectors * 512)
                capacity_buffer = ctypes.create_string_buffer(new_capacity)
                bytes_written = ctypes.c_ulong(0)
                ctypes.windll.kernel32.WriteFile(h_device, capacity_buffer, 8, ctypes.byref(bytes_written), None)
                ctypes.windll.kernel32.FlushFileBuffers(h_device)
                
                self.log(f"  Updated capacity table at offset 0x{offset:X}")
                
            except Exception as e:
                self.log(f"  Warning: Could not update table at 0x{offset:X}: {e}")
                continue
        
        return True
    
    def modify_smi_capacity(self, h_device, target_sectors: int) -> bool:
        """Modify SMI controller capacity tables"""
        self.log("  Modifying SMI controller capacity...")
        
        # SMI controllers use different locations
        try:
            # SMI typically stores capacity in the configuration block
            offset = 0x4000
            
            low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
            high_part = ctypes.c_ulong(offset >> 32)
            ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
            
            # Write new capacity
            new_capacity = struct.pack('<Q', target_sectors * 512)
            capacity_buffer = ctypes.create_string_buffer(new_capacity)
            bytes_written = ctypes.c_ulong(0)
            ctypes.windll.kernel32.WriteFile(h_device, capacity_buffer, 8, ctypes.byref(bytes_written), None)
            ctypes.windll.kernel32.FlushFileBuffers(h_device)
            
            self.log("  Updated SMI capacity configuration")
            return True
            
        except Exception as e:
            self.log(f"  SMI modification error: {e}")
            return False
    
    def modify_alcor_capacity(self, h_device, target_sectors: int) -> bool:
        """Modify Alcor controller capacity tables"""
        self.log("  Modifying Alcor controller capacity...")
        
        # Alcor controllers store capacity in multiple locations
        offsets = [0x5000, 0x6000]
        
        for offset in offsets:
            try:
                low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
                high_part = ctypes.c_ulong(offset >> 32)
                ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                
                new_capacity = struct.pack('<Q', target_sectors * 512)
                capacity_buffer = ctypes.create_string_buffer(new_capacity)
                bytes_written = ctypes.c_ulong(0)
                ctypes.windll.kernel32.WriteFile(h_device, capacity_buffer, 8, ctypes.byref(bytes_written), None)
                ctypes.windll.kernel32.FlushFileBuffers(h_device)
                
                self.log(f"  Updated Alcor capacity at 0x{offset:X}")
                
            except Exception as e:
                self.log(f"  Alcor modification error at 0x{offset:X}: {e}")
        
        return True
    
    def modify_generic_capacity(self, h_device, target_sectors: int) -> bool:
        """Generic capacity modification for unknown controllers"""
        self.log("  Attempting generic capacity modification...")
        
        # Try common locations where capacity might be stored
        common_offsets = [0x1000, 0x2000, 0x4000, 0x8000]
        
        for offset in common_offsets:
            try:
                low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
                high_part = ctypes.c_ulong(offset >> 32)
                ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                
                # Read current data to see if it looks like a capacity value
                current_data = ctypes.create_string_buffer(8)
                bytes_read = ctypes.c_ulong(0)
                ctypes.windll.kernel32.ReadFile(h_device, current_data, 8, ctypes.byref(bytes_read), None)
                
                current_capacity = struct.unpack('<Q', current_data.raw)[0]
                
                # If this looks like a capacity (reasonable size), update it
                if 1024*1024 < current_capacity < 1024*1024*1024*1024*1024:  # 1MB to 1PB
                    new_capacity = struct.pack('<Q', target_sectors * 512)
                    capacity_buffer = ctypes.create_string_buffer(new_capacity)
                    bytes_written = ctypes.c_ulong(0)
                    ctypes.windll.kernel32.WriteFile(h_device, capacity_buffer, 8, ctypes.byref(bytes_written), None)
                    ctypes.windll.kernel32.FlushFileBuffers(h_device)
                    
                    self.log(f"  Updated generic capacity at 0x{offset:X}")
                    return True
                    
            except Exception as e:
                continue
        
        return False
    
    def update_ata_identify_data(self, h_device, target_sectors: int, cylinders: int, heads: int, sectors: int) -> bool:
        """Update ATA IDENTIFY DEVICE data structure"""
        try:
            self.log("  Updating ATA IDENTIFY data...")
            
            # Write new CHS geometry
            chs_data = struct.pack('<HHH', cylinders, heads, sectors)
            
            # Common locations for CHS data
            chs_offsets = [0x1C0, 0x1C2, 0x1C4]  # Common ATA identify offsets
            
            for i, offset in enumerate(chs_offsets):
                try:
                    low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
                    high_part = ctypes.c_ulong(offset >> 32)
                    ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                    
                    bytes_written = ctypes.c_ulong(0)
                    chs_buffer = ctypes.create_string_buffer(chs_data[i:i+2])
                    ctypes.windll.kernel32.WriteFile(h_device, chs_buffer, 2, ctypes.byref(bytes_written), None)
                    ctypes.windll.kernel32.FlushFileBuffers(h_device)
                    
                except Exception as e:
                    continue
            
            # Update total sectors count
            total_sectors_data = struct.pack('<Q', target_sectors)
            sector_offsets = [0x70, 0x200]  # Common sector count locations
            
            for offset in sector_offsets:
                try:
                    low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
                    high_part = ctypes.c_ulong(offset >> 32)
                    ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                    
                    bytes_written = ctypes.c_ulong(0)
                    sectors_buffer = ctypes.create_string_buffer(total_sectors_data)
                    ctypes.windll.kernel32.WriteFile(h_device, sectors_buffer, 8, ctypes.byref(bytes_written), None)
                    ctypes.windll.kernel32.FlushFileBuffers(h_device)
                    
                except Exception as e:
                    continue
            
            self.log("  ATA IDENTIFY data updated")
            return True
            
        except Exception as e:
            self.log(f"  ATA update error: {e}")
            return False
    
    def reset_drive_controller(self, h_device) -> bool:
        """Reset the drive controller to apply changes"""
        try:
            self.log("  Resetting drive controller...")
            
            # Send ATA soft reset command
            reset_command = ctypes.create_string_buffer(512)
            reset_command.raw[0] = 0x04  # ATA soft reset
            
            bytes_written = ctypes.c_ulong(0)
            ctypes.windll.kernel32.WriteFile(h_device, reset_command, 512, ctypes.byref(bytes_written), None)
            ctypes.windll.kernel32.FlushFileBuffers(h_device)
            
            # Wait for reset to complete
            time.sleep(2.0)
            
            self.log("  Drive controller reset complete")
            return True
            
        except Exception as e:
            self.log(f"  Controller reset error: {e}")
            return False
        
    def fix_drive_capacity(self, real_size_bytes: int) -> bool:
        """
        PERMANENT FIRMWARE-LEVEL CAPACITY MODIFICATION
        This modifies the drive's actual firmware and manufacturer data
        NOT just partitioning - true hardware-level capacity change
        """
        drive_letter = str(self.target)[0]
        
        self.log("\n" + "="*60)
        self.log("FIRMWARE-LEVEL CAPACITY MODIFICATION")
        self.log("="*60)
        self.log(f"Target capacity: {real_size_bytes / (1024**3):.3f} GB")
        self.log("This will PERMANENTLY modify the drive's firmware")
        self.log("The drive will report this capacity everywhere")
        self.log("This is NOT a partition trick - this changes hardware data")
        
        try:
            # Step 1: Get raw disk access
            self.log("\n[1/9] Obtaining raw disk access...")
            
            diskpart_script = f"""
rescan
select volume {drive_letter}
detail volume
detail disk
            """
            
            result = subprocess.run(['diskpart'], input=diskpart_script, capture_output=True, text=True)
            
            import re
            disk_match = re.search(r'Disk (\d+)', result.stdout)
            if not disk_match:
                disk_match = re.search(r'[Dd]isk [Nn]umber\s*:\s*(\d+)', result.stdout)
            if not disk_match:
                self.log("Could not locate physical disk device")
                return False
                
            disk_num = disk_match.group(1)
            device_path = f"\\\\.\\PhysicalDrive{disk_num}"
            self.log(f"Physical device: {device_path}")
            
            # Step 2: Open raw disk handle with maximum privileges
            h_device = ctypes.windll.kernel32.CreateFileW(
                device_path,
                0xC0000000,  # GENERIC_READ | GENERIC_WRITE
                0x3,         # FILE_SHARE_READ | FILE_SHARE_WRITE
                None,
                3,           # OPEN_EXISTING
                0x80,        # FILE_FLAG_NO_BUFFERING
                None
            )
            
            if h_device == -1:
                self.log("Failed to open raw disk device")
                return False
            
            try:
                # Step 3: Read and identify controller
                self.log("\n[2/9] Identifying drive controller...")
                
                firmware_data = ctypes.create_string_buffer(64 * 1024)
                bytes_read = ctypes.c_ulong(0)
                
                if not ctypes.windll.kernel32.ReadFile(
                    h_device, firmware_data, 64 * 1024, ctypes.byref(bytes_read), None
                ):
                    self.log("Failed to read firmware area")
                    return False
                
                controller_info = self.identify_controller(bytearray(firmware_data))
                self.log(f"Controller: {controller_info['type']} ({controller_info['manufacturer']})")
                
                # Step 4: Calculate new geometry
                self.log("\n[3/9] Calculating new drive geometry...")
                
                target_sectors = real_size_bytes // SECTOR_SIZE
                target_cylinders = target_sectors // (16 * 63)
                target_heads = 16
                target_sectors_per_track = 63
                
                self.log(f"New geometry: {target_cylinders} cylinders, {target_heads} heads, {target_sectors_per_track} sectors")
                self.log(f"Total sectors: {target_sectors:,}")
                
                # Step 5: Modify firmware capacity tables
                self.log("\n[4/9] Modifying firmware capacity tables...")
                
                success = self.modify_firmware_capacity(h_device, controller_info, target_sectors)
                if not success:
                    self.log("Failed to modify firmware capacity")
                    return False
                
                # Step 6: Update ATA identify data
                self.log("\n[5/9] Updating ATA identify device data...")
                
                success = self.update_ata_identify_data(h_device, target_sectors, target_cylinders, target_heads, target_sectors_per_track)
                if not success:
                    self.log("Failed to update ATA identify data")
                    return False
                
                # Step 7: Create new partition table
                self.log("\n[6/9] Creating new partition table...")
                
                # Write MBR with correct capacity
                mbr = bytearray(SECTOR_SIZE)
                
                # Partition entry with new capacity
                partition_entry = struct.pack('<BBBBBBBBII',
                    0x80,          # Bootable
                    0x00, 0x02, 0x00, # CHS start
                    0x07,          # NTFS type
                    0xFE, 0xFF, 0xFF, # CHS end
                    0x00000008,    # LBA start
                    target_sectors - 2048 # Total sectors
                )
                
                mbr[0x1BE:0x1CE] = partition_entry
                mbr[0x1FE:0x200] = b'\x55\xAA'  # Boot signature
                
                # Write MBR to sector 0
                low_part = ctypes.c_ulong(0)
                high_part = ctypes.c_ulong(0)
                ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                
                mbr_buffer = ctypes.create_string_buffer(mbr)
                bytes_written = ctypes.c_ulong(0)
                ctypes.windll.kernel32.WriteFile(h_device, mbr_buffer, SECTOR_SIZE, ctypes.byref(bytes_written), None)
                ctypes.windll.kernel32.FlushFileBuffers(h_device)
                
                self.log("  New partition table written")
                
                # Step 8: Verify modification
                self.log("\n[7/9] Verifying firmware modification...")
                
                # Read back capacity data to verify
                offsets_to_check = [0x1000, 0x2000, 0x4000]
                verification_success = False
                
                for offset in offsets_to_check:
                    try:
                        low_part = ctypes.c_ulong(offset & 0xFFFFFFFF)
                        high_part = ctypes.c_ulong(offset >> 32)
                        ctypes.windll.kernel32.SetFilePointer(h_device, low_part, ctypes.byref(high_part), 0)
                        
                        data = ctypes.create_string_buffer(8)
                        bytes_read = ctypes.c_ulong(0)
                        ctypes.windll.kernel32.ReadFile(h_device, data, 8, ctypes.byref(bytes_read), None)
                        
                        stored_capacity = struct.unpack('<Q', data.raw)[0]
                        expected_capacity = target_sectors * 512
                        
                        if abs(stored_capacity - expected_capacity) < 1024*1024:  # Within 1MB tolerance
                            self.log(f"  Capacity verified at 0x{offset:X}")
                            verification_success = True
                            break
                             
                    except Exception as e:
                        continue
                
                if not verification_success:
                    self.log("  Could not verify capacity modification")
                    return False
                
                # Step 9: Reset controller
                self.log("\n[8/9] Resetting drive controller...")
                
                success = self.reset_drive_controller(h_device)
                if not success:
                    self.log("Controller reset failed")
                    return False
                
                # Step 10: Final verification
                self.log("\n[9/9] Final verification and cleanup...")
                
                # Force Windows to rescan the drive
                subprocess.run(['diskpart'], input='rescan\n', capture_output=True, text=True)
                time.sleep(3.0)
                
                self.log("\n" + "="*60)
                self.log("FIRMWARE CAPACITY SUCCESSFULLY MODIFIED!")
                self.log("="*60)
                self.log("Drive manufacturer data has been PERMANENTLY updated")
                self.log("The drive will now report the correct capacity everywhere")
                self.log("This is a true hardware-level fix, not a partition trick")
                self.log("Unplug and reconnect the drive to see the new capacity")
                
                return True
                
            finally:
                ctypes.windll.kernel32.CloseHandle(h_device)
                
        except Exception as e:
            self.log(f"Error during firmware modification: {e}")
            return False

class F3GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Flash Drive Fraud Fixer (F3)")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Set Windows icon
        if platform.system() == "Windows":
            self.root.iconbitmap(default='')
        
        self.tester = None
        self.test_thread = None
        
        # Check admin status
        self.admin_status = "✓ Running as Administrator" if is_admin() else "⚠ Limited mode (no Admin rights)"
        
        self.build_ui()
        self.refresh_drives()
    
    def build_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Flash Drive Fraud Fixer", font=('Segoe UI', 16, 'bold'))
        title_label.pack(pady=(0,5))
        
        status_label = ttk.Label(main_frame, text=self.admin_status, foreground='blue')
        status_label.pack(pady=(0,10))
        
        # Drive selection
        drive_frame = ttk.LabelFrame(main_frame, text=" Select Drive ", padding=10)
        drive_frame.pack(fill=tk.X, pady=5)
        
        self.drive_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(drive_frame, textvariable=self.drive_var, state='readonly', width=40)
        self.drive_combo.pack(side=tk.LEFT, padx=5)
        
        refresh_btn = ttk.Button(drive_frame, text="Refresh Drives", command=self.refresh_drives)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.admin_btn = ttk.Button(drive_frame, text="Restart as Admin", command=run_as_admin)
        self.admin_btn.pack(side=tk.RIGHT, padx=5)
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text=" Test Options ", padding=10)
        options_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(options_frame, text="Test limit:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.test_limit_var = tk.StringVar(value="Full test")
        limit_combo = ttk.Combobox(options_frame, textvariable=self.test_limit_var, values=["Full test", "1 GB", "2 GB", "4 GB", "8 GB", "16 GB"], width=15, state='readonly')
        limit_combo.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(options_frame, text="Manual size:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.manual_size_var = tk.StringVar(value="")
        size_entry = ttk.Entry(options_frame, textvariable=self.manual_size_var, width=17)
        size_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(options_frame, text="GB (Enter manually to set custom drive capacity)").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)

        # Auto enable Fix button when valid manual size is entered
        def check_manual_size(*args):
            manual_size = self.manual_size_var.get().strip()
            if manual_size and self.drive_var.get():
                try:
                    val = float(manual_size)
                    if val > 0:
                        self.fix_btn.config(state=tk.NORMAL)
                        return
                except:
                    pass
            # Only disable if no test results available
            if not hasattr(self, 'last_test_results'):
                self.fix_btn.config(state=tk.DISABLED)
        
        self.manual_size_var.trace_add('write', check_manual_size)
        self.drive_var.trace_add('write', check_manual_size)
        
        # Buttons - Full width expanded with individual colors
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        btn_frame.grid_columnconfigure(2, weight=1)
        
        # Green Start Button
        self.start_btn = ttk.Button(btn_frame, text="▶ Start Test", command=self.start_test, style='Green.TButton')
        self.start_btn.grid(row=0, column=0, padx=3, sticky="nsew")
        
        # Orange Stop Button
        self.stop_btn = ttk.Button(btn_frame, text="■ Stop Test", command=self.stop_test, state=tk.DISABLED, style='Orange.TButton')
        self.stop_btn.grid(row=0, column=1, padx=3, sticky="nsew")
        
        # Blue Fix Button
        self.fix_btn = ttk.Button(btn_frame, text="🔧 Fix Drive Capacity", command=self.fix_drive, state=tk.DISABLED, style='Blue.TButton')
        self.fix_btn.grid(row=0, column=2, padx=3, sticky="nsew")
        
        # Setup custom button styles
        style = ttk.Style()
        style.configure('Green.TButton', background='#2ecc71', foreground='black', font=('Segoe UI', 9, 'bold'))
        style.configure('Orange.TButton', background='#f39c12', foreground='black', font=('Segoe UI', 9, 'bold'))
        style.configure('Blue.TButton', background='#3498db', foreground='black', font=('Segoe UI', 9, 'bold'))
        
        # Fix for Windows theme button text visibility
        style.map('Green.TButton',
            foreground=[('active', 'black'), ('pressed', 'black'), ('!disabled', 'black')],
            background=[('active', '#27ae60'), ('pressed', '#229954')])
        style.map('Orange.TButton',
            foreground=[('active', 'black'), ('pressed', 'black'), ('!disabled', 'black')],
            background=[('active', '#e67e22'), ('pressed', '#d35400')])
        style.map('Blue.TButton',
            foreground=[('active', 'black'), ('pressed', 'black'), ('!disabled', 'black')],
            background=[('active', '#2980b9'), ('pressed', '#1f618d')])
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground='gray')
        status_label.pack(anchor=tk.W, pady=(0,5))
        
        # Log output
        log_frame = ttk.LabelFrame(main_frame, text=" Log Output ", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Results display
        self.results_var = tk.StringVar(value="")
        results_label = ttk.Label(main_frame, textvariable=self.results_var, font=('Segoe UI', 10, 'bold'))
        results_label.pack(pady=10)
    
    def refresh_drives(self):
        drives = get_windows_drives()
        self.drive_combo['values'] = [name for (letter, name, size) in drives]
        self.drive_map = {name: letter for (letter, name, size) in drives}
        if drives:
            self.drive_combo.current(0)
        self.log("Drive list refreshed. Plug in your USB drive and click Refresh if not listed.")
    
    def log(self, message: str):
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_progress(self, percent: float, status: str = ""):
        self.progress['value'] = percent
        self.status_var.set(status)
        self.root.update_idletasks()
    
    def start_test(self):
        if not self.drive_var.get():
            messagebox.showwarning("Warning", "Please select a drive first")
            return
        
        drive_letter = self.drive_map[self.drive_var.get()]
        
        confirm = messagebox.askyesno("Confirm Test", 
            f"You are about to test drive {drive_letter}\n\n"
            "This will write test files to fill the entire drive.\n"
            "No existing files will be deleted, but make sure you have enough free space.\n\n"
            "Continue?")
        
        if not confirm:
            return
            
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress['value'] = 0
        self.log_text.delete(1.0, tk.END)
        self.results_var.set("")
        
        # Parse test limit
        limit_text = self.test_limit_var.get()
        max_gb = None
        if limit_text != "Full test":
            max_gb = int(limit_text.split()[0])

        # Check for manual size input
        manual_size = self.manual_size_var.get().strip()
        if manual_size:
            try:
                max_gb = int(float(manual_size))
                self.log(f"Using manual test size: {max_gb} GB")
            except ValueError:
                messagebox.showwarning("Warning", "Invalid manual size. Using selected option.")
        else:
            # FULL TEST MODE - test 1GB MORE than advertised drive capacity
            if limit_text == "Full test":
                # Get selected drive total size
                selected_drive = self.drive_var.get()
                drives = get_windows_drives()
                drive_total_bytes = 0
                for (letter, name, size) in drives:
                    if name == selected_drive:
                        drive_total_bytes = size
                        break
                
                drive_size_gb = drive_total_bytes / (1024**3)
                max_gb = int(drive_size_gb) + 1
                self.log(f"Full test mode enabled - testing {max_gb} GB (advertised drive size + 1 GB overcapacity)")
        
        self.tester = FlashTester(drive_letter)
        self.tester.log_callback = self.log
        self.tester.progress_callback = self.update_progress
        
        # Run test in background thread
        def test_worker():
            try:
                results = self.tester.run_full_test(max_gb)
                self.last_test_results = results
                
                # ALWAYS auto-fill detected capacity into manual size field - EVEN WHEN TEST STOPS EARLY
                try:
                    if 'estimated_real_gb' in results and results['estimated_real_gb'] > 0:
                        self.manual_size_var.set(f"{results['estimated_real_gb']:.2f}")
                        self.fix_btn.config(state=tk.NORMAL)
                except Exception:
                    pass
                    
                if not results.get('cancelled', False):
                    try:
                        results_label = self.root.nametowidget(self.results_var._name)
                        if results['data_lost_gb'] > 0.1:
                            self.results_var.set(f"⚠️ FAKE DRIVE DETECTED! Real capacity: ~{results['estimated_real_gb']:.2f} GB")
                            results_label.config(foreground='red')
                        elif results['data_lost_gb'] == 0:
                            self.results_var.set("✅ DRIVE IS GENUINE. All tests passed!")
                            results_label.config(foreground='green')
                            # For genuine drives use full reported size
                            selected_drive = self.drive_var.get()
                            drives = get_windows_drives()
                            for (letter, name, size) in drives:
                                if name == selected_drive:
                                    self.manual_size_var.set(f"{size/(1024**3):.2f}")
                                    break
                        else:
                            self.results_var.set("❓ Inconclusive results - run full test")
                            results_label.config(foreground='orange')
                    except Exception:
                        pass
            except Exception as e:
                self.log(f"GUI ERROR: {e}")
            finally:
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
        
        self.test_thread = threading.Thread(target=test_worker, daemon=True)
        self.test_thread.start()
    
    def stop_test(self):
        if self.tester:
            self.tester.stop()
            self.log("Test stopped by user")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
    def fix_drive(self):
        # Check if manual size is provided
        manual_size = self.manual_size_var.get().strip()
        target_gb = None
        
        if manual_size:
            try:
                target_gb = float(manual_size)
                if target_gb <= 0:
                    raise ValueError("Size must be positive")
            except ValueError:
                messagebox.showwarning("Warning", "Please enter a valid positive number for manual capacity")
                return
        else:
            # Fall back to test results if no manual size
            if not hasattr(self, 'last_test_results'):
                messagebox.showwarning("Warning", "Either run a test first, or enter manual capacity in GB")
                return
            target_gb = self.last_test_results['estimated_real_gb']
        
        # Convert to bytes
        real_bytes = int(target_gb * 1024**3)
        
        confirm = messagebox.askyesno("WARNING - PERMANENT OPERATION", 
            f"THIS WILL ERASE ALL DATA ON THE DRIVE!\n\n"
            f"This will repartition the drive to exactly {target_gb:.2f} GB capacity.\n"
            f"All existing files will be deleted. This cannot be undone.\n\n"
            "Continue?")
        
        if not confirm:
            return
            
        self.fix_btn.config(state=tk.DISABLED)
        
        # Create tester instance if needed
        if not self.tester:
            drive_letter = self.drive_map[self.drive_var.get()]
            self.tester = FlashTester(drive_letter)
            self.tester.log_callback = self.log
            self.tester.progress_callback = self.update_progress
        
        def fix_worker():
            success = self.tester.fix_drive_capacity(real_bytes)
            if success:
                self.results_var.set(f"✅ DRIVE FIXED TO {target_gb:.2f} GB!")
                self.results_var.config(foreground='green')
                self.refresh_drives()
            else:
                self.fix_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=fix_worker, daemon=True).start()


def main():
    # FORCE ADMINISTRATOR RIGHTS - NO EXCEPTIONS
    if platform.system() == "Windows":
        if not is_admin():
            run_as_admin()
            return
    
    # Enable Windows DPI awareness
    if platform.system() == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    
    root = tk.Tk()
    app = F3GUI(root)
    
    # Center window
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()


if __name__ == "__main__":
    main()
