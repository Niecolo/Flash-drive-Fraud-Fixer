# Flash Drive Fraud Fixer 
## Detect and Fix Fake / Counterfeit USB Flash Drives

Windows GUI application that accurately tests USB flash drives for fake capacity, detects real usable size, and can permanently fix counterfeit drives at the firmware level.

---

### ⚠️ IMPORTANT SAFETY WARNING
This software performs low-level disk operations. **USE AT YOUR OWN RISK**. Always backup important data before testing or modifying any drive. This tool is for advanced users only.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| ✅ **Accurate Fake Drive Detection** | Advanced testing algorithm that cannot be fooled by fake drive controllers |
| ✅ **Real Capacity Estimation** | Precisely identifies the actual usable capacity of counterfeit drives |
| ✅ **Firmware Level Repair** | Permanently fixes fake drives by modifying controller capacity tables (NOT just partitioning) |
| ✅ **Modern Windows GUI** | Easy to use graphical interface with progress tracking and detailed logging |
| ✅ **Anti-Cheat Test Patterns** | Special test data generation that bypasses drive cache and controller tricks |
| ✅ **Multi-Controller Support** | Works with Phison, SMI, Alcor, Innostor, Genesys and most common flash controllers |
| ✅ **Automatic Drive Detection** | Automatically lists and detects removable USB drives |
| ✅ **Full Verification** | Complete write + read verification cycle with detailed corruption analysis |

---

## 🚀 How It Works

Fake flash drives work by lying about their real capacity in the controller firmware. When you write data beyond the actual capacity, the drive just wraps around, overwriting old data without any warning.

uses an advanced testing methodology:
<img width="1365" height="722" alt="image" src="https://github.com/user-attachments/assets/4f14198d-9ebd-489f-aa0c-5dd87e364f95" />

1.  Writes unique verifiable test patterns to the entire drive
2.  Reads back and verifies every sector
3.  Detects exactly where corruption starts
4.  Calculates real usable capacity
5.  **Can permanently modify the drive firmware** to report the correct true capacity

This is not a simple partition trick - this modifies the drive's internal firmware tables so it reports the correct capacity everywhere, permanently.

---

## 📋 System Requirements

- Windows 10 / Windows 11
- Python 3.8+ (for running from source)
- **Administrator privileges required** for full functionality and drive repair

---

## 🔧 Installation

### Pre-built EXE (Recommended)
1.  Download the latest release from Releases
2.  Right click `F3 Flash Fixer.exe` and select **Run as Administrator**

### Run From Source
```bash
# Clone repository
git clone https://github.com/yourusername/f3-flash-fixer.git
cd f3-flash-fixer

# Run the application
python "Flash Drive Fraud Fixer .py"
```

### Build Standalone EXE
```bash
pip install pyinstaller
build_dist.bat
```
Compiled EXE will be created in `dist/` folder.

---

## 📖 Usage Instructions

### Testing a Drive
1.  Plug in your USB flash drive
2.  Run F3 as Administrator
3.  Select your drive from the dropdown list
4.  Click **▶ Start Test**
5.  Wait for the test to complete (this can take a long time depending on drive size)

### Fixing a Fake Drive
1.  First run a full test on the drive
2.  The application will automatically detect if the drive is fake
3.  The real estimated capacity will be shown in the results
4.  Enter the real capacity in GB
5.  Click **🔧 Fix Drive Capacity**
6.  Wait for the firmware modification process to complete
7.  Unplug and reconnect the drive - it will now permanently show the correct capacity

---

## 🛡️ What Makes This Different

Most fake drive testers:
- Can be fooled by drive cache and controller tricks
- Only give you an estimate of real capacity
- Only create a partition at real size (drive still reports fake size everywhere else)

F3:
- Uses anti-cheat test patterns that cannot be cached or predicted
- Modifies the actual controller firmware at the hardware level
- Drive will report correct capacity in BIOS, Windows, Linux, Mac, and every other device
- This is a permanent hardware level fix, not a software workaround

---

## 📊 Test Results Explanation

| Result | Meaning |
|--------|---------|
| ✅ **DRIVE IS GENUINE** | All data verified correctly. Drive is real. |
| ⚠️ **DRIVE APPEARS TO BE FAKE** | Drive has been identified as counterfeit. Real capacity will be shown. |
| ❓ **Inconclusive results** | Test interrupted or not completed. Run full test again. |

---

## ⚙️ Technical Details

- Tests in 1GB chunks with unique per-sector identifiers
- Uses multiple verification layers: magic headers, sector numbering, checksums
- Bypasses all operating system caches and buffer layers
- Automatically detects drive controller type
- Modifies controller specific capacity tables at known firmware offsets
- Updates ATA identify device data
- Writes corrected MBR partition table
- Resets drive controller to apply changes

---

## 🚨 Disclaimer

This software is provided for educational purposes only. Modifying drive firmware may void warranties and could potentially brick drives. Always test on drives you don't care about first. The author is not responsible for any data loss or hardware damage.

---

## 📄 License

This project is open source under the MIT License.

Inspired by the original `F3 - Fight Flash Fraud` project by Michel Machado.

---

## 💡 Contributing

Pull requests, bug reports, and controller signature additions are welcome.

---

## ⭐ Support

If you found this software useful, please give it a star on GitHub!
