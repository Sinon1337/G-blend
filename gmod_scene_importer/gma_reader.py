import struct
import os
import threading

_GMA_WRITE_LOCK = threading.Lock()

class GMAReader:
    def __init__(self, filepath):
        self.filepath = filepath
        self.file = None
        self.file_entries = [] # List of objects with name, size, offset
        self.addon_info = {}
        
    def __enter__(self):
        import io
        import lzma
        
        self.file = open(self.filepath, 'rb')
        ident = self.file.read(4)
        self.file.seek(0)
        
        if ident != b'GMAD':
            # This is likely a compressed workshop .bin file
            try:
                raw_data = self.file.read()
                self.file.close()
                decompressed = lzma.decompress(raw_data)
                self.file = io.BytesIO(decompressed)
                print(f"[GMAReader] LZMA Decompressed: {self.filepath}")
            except Exception as e:
                # Fallback: reopen as plain file
                self.file = open(self.filepath, 'rb')
                print(f"[GMAReader] LZMA Decompression failed for {self.filepath}: {e}")
                
        self.read_header()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()

    def read_string(self):
        result = b""
        while True:
            char = self.file.read(1)
            if not char or char == b'\x00':
                break
            result += char
        return result.decode('utf-8', errors='replace')

    def read_header(self):
        # Header: GMAD (4 chars)
        ident = self.file.read(4)
        if ident != b'GMAD':
            raise ValueError(f"Invalid GMA file: {self.filepath}")
            
        version = struct.unpack('B', self.file.read(1))[0]
        steamid = self.file.read(8) # 64-bit int
        timestamp = self.file.read(8) # 64-bit int
        
        if version > 1:
            content_desc = self.read_string()
        
        addon_name = self.read_string()
        addon_desc = self.read_string()
        addon_author = self.read_string()
        addon_version = struct.unpack('i', self.file.read(4))[0]
        
        self.addon_info = {
            'name': addon_name,
            'desc': addon_desc,
            'author': addon_author,
            'version': addon_version
        }
        
        # Read File List
        self.file_entries = []
        
        while True:
            file_number = struct.unpack('I', self.file.read(4))[0]
            if file_number == 0:
                break
                
            name = self.read_string()
            size = struct.unpack('q', self.file.read(8))[0] # int64
            crc = struct.unpack('I', self.file.read(4))[0]
            
            # Create a simple object for entry
            class GMAEntry:
                pass
            entry = GMAEntry()
            entry.name = name
            entry.size = size
            entry.crc = crc
            entry.offset = 0
            self.file_entries.append(entry)
            
        # Organize offsets
        data_start = self.file.tell()
        current_offset = data_start
        for entry in self.file_entries:
            entry.offset = current_offset
            current_offset += entry.size

    def extract_files(self, target_dir, allowed_names=None):
        """
        Extracts files to target_dir. 
        If allowed_names (set) is provided, only files in that set are extracted.
        """
        if not self.file:
            raise RuntimeError("File not open")
            
        count = 0
        for entry in self.file_entries:
            rel_path = entry.name.replace('\\', '/')
            if rel_path.startswith('/'): rel_path = rel_path[1:]
            lower_path = rel_path.lower()
            
            # Security
            if '..' in rel_path:
                continue
                
            # Filter
            if allowed_names is not None:
                # Surgical check: must match exactly what scanner found
                if lower_path not in allowed_names:
                    continue

            full_path = os.path.join(target_dir, rel_path)
            dest_folder = os.path.dirname(full_path)
            
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder, exist_ok=True)
            
            try:
                self.file.seek(entry.offset)
                data = self.file.read(entry.size)
                
                # Prevent race conditions during multithreaded extraction
                import threading
                if not hasattr(self, "_write_lock"):
                    # Use a global lock attached to the module if needed, or just a simple lock
                    pass
                
                with _GMA_WRITE_LOCK:
                    with open(full_path, 'wb') as f:
                        f.write(data)
                count += 1
            except Exception as e:
                print(f"[GMA] Failed to extract {rel_path}: {e}")
                
        return count

    def get_file_content(self, entry_name_or_obj):
        """Returns bytes of a specific file in the archive."""
        if not self.file: return None
        
        target = None
        if isinstance(entry_name_or_obj, str):
            low_name = entry_name_or_obj.lower().replace('\\', '/').lstrip('/')
            for e in self.file_entries:
                if e.name.lower().replace('\\', '/').lstrip('/') == low_name:
                    target = e
                    break
        else:
            target = entry_name_or_obj
            
        if target:
            self.file.seek(target.offset)
            return self.file.read(target.size)
        return None
