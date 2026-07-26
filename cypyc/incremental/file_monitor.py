"""文件监控器 - 实时检测Cypy源文件变更"""

import os
import time
import threading
from typing import Callable, List, Set, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent


class FileChangeEvent:
    """文件变更事件"""
    
    def __init__(self, file_path: str, event_type: str):
        self.file_path = file_path
        self.event_type = event_type  # 'modified', 'created', 'deleted'
        self.timestamp = time.time()


class CypyFileMonitor:
    """Cypy文件监控器"""
    
    def __init__(self, watch_dirs: List[str], callback: Callable[[List[FileChangeEvent]], None], 
                 debounce_delay: float = 0.5, patterns: Optional[List[str]] = None):
        """
        初始化文件监控器
        
        参数:
            watch_dirs: 要监控的目录列表
            callback: 变更事件回调函数，接收变更事件列表
            debounce_delay: 防抖延迟（秒），默认0.5秒
            patterns: 文件匹配模式列表，默认监控.cypy和带#!bin cypy头的.py文件
        """
        self._watch_dirs = [os.path.abspath(d) for d in watch_dirs]
        self._callback = callback
        self._debounce_delay = debounce_delay
        self._patterns = patterns or [".cypy"]
        self._observer = Observer()
        self._event_handler = _CypyFileEventHandler(self)
        self._pending_events: List[FileChangeEvent] = []
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_lock = threading.Lock()
        self._is_running = False
        self._watched_files: Set[str] = set()
        
    def _is_cypy_file(self, file_path: str) -> bool:
        """检查文件是否是Cypy文件"""
        # 检查文件扩展名
        if any(file_path.endswith(pattern) for pattern in self._patterns):
            return True
        
        # 检查.py文件是否有#!bin cypy头
        if file_path.endswith(".py"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    return first_line == "#!bin cypy"
            except Exception:
                pass
        
        return False
    
    def _schedule_callback(self):
        """调度回调执行"""
        with self._debounce_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            
            self._debounce_timer = threading.Timer(
                self._debounce_delay,
                self._execute_callback
            )
            self._debounce_timer.start()
    
    def _execute_callback(self):
        """执行回调函数"""
        with self._debounce_lock:
            events = list(self._pending_events)
            self._pending_events.clear()
        
        if events:
            try:
                self._callback(events)
            except Exception as e:
                print(f"[CypyFileMonitor] Callback error: {e}")
    
    def _on_file_changed(self, file_path: str, event_type: str):
        """处理文件变更事件"""
        if not self._is_cypy_file(file_path):
            return
        
        # 避免重复事件（watchdog可能会触发多次）
        with self._debounce_lock:
            # 检查是否已有相同文件的待处理事件
            existing = [e for e in self._pending_events if e.file_path == file_path]
            if existing:
                # 更新事件类型和时间戳
                existing[0].event_type = event_type
                existing[0].timestamp = time.time()
            else:
                self._pending_events.append(FileChangeEvent(file_path, event_type))
        
        self._schedule_callback()
    
    def start(self):
        """启动监控器"""
        if self._is_running:
            return
        
        # 注册监控目录
        for watch_dir in self._watch_dirs:
            if os.path.exists(watch_dir):
                self._observer.schedule(
                    self._event_handler,
                    watch_dir,
                    recursive=True
                )
        
        self._observer.start()
        self._is_running = True
        
        # 初始扫描已存在的Cypy文件
        self._scan_existing_files()
        
        print(f"[CypyFileMonitor] Started monitoring {len(self._watch_dirs)} directories")
    
    def stop(self):
        """停止监控器"""
        if not self._is_running:
            return
        
        self._is_running = False
        
        # 取消防抖定时器
        with self._debounce_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
        
        self._observer.stop()
        self._observer.join()
        
        print(f"[CypyFileMonitor] Stopped")
    
    def _scan_existing_files(self):
        """扫描已存在的Cypy文件"""
        for watch_dir in self._watch_dirs:
            for root, dirs, files in os.walk(watch_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if self._is_cypy_file(file_path):
                        self._watched_files.add(file_path)
        
        print(f"[CypyFileMonitor] Found {len(self._watched_files)} Cypy files to monitor")
    
    def get_watched_files(self) -> Set[str]:
        """获取当前监控的文件列表"""
        return set(self._watched_files)


class _CypyFileEventHandler(FileSystemEventHandler):
    """内部文件系统事件处理器"""
    
    def __init__(self, monitor: CypyFileMonitor):
        self._monitor = monitor
    
    def on_modified(self, event: FileModifiedEvent):
        """处理文件修改事件"""
        if not event.is_directory:
            self._monitor._on_file_changed(event.src_path, "modified")
    
    def on_created(self, event: FileCreatedEvent):
        """处理文件创建事件"""
        if not event.is_directory:
            self._monitor._on_file_changed(event.src_path, "created")
    
    def on_deleted(self, event: FileDeletedEvent):
        """处理文件删除事件"""
        if not event.is_directory:
            self._monitor._on_file_changed(event.src_path, "deleted")
