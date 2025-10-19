# memory_facade.py
"""
Unified memory bridge facade that provides consistent interface
regardless of backend implementation (Rust or Python).
"""
from typing import List, Optional, Union, Dict, Any
import os

class UnifiedMemoryBridge:
    """
    Facade that provides unified interface for memory operations,
    abstracting away the backend implementation details.
    """
    
    def __init__(self, use_rust: bool = None, db_session = None):
        self.db_session = db_session
        self.use_rust = use_rust if use_rust is not None else self._should_use_rust()
        self._backend = None
        self._persistence = None
        
        if self.db_session:
            from memory_persistence import MemoryNodeDAO
            self._persistence = MemoryNodeDAO(self.db_session)
    
    def _should_use_rust(self) -> bool:
        """Determine whether to use Rust backend based on environment and availability"""
        try:
            # Check if Rust module is available
            import memlibrary
            return os.getenv('USE_RUST_MEMORY', 'true').lower() == 'true'
        except ImportError:
            return False
    
    @property
    def backend(self):
        """Lazy initialization of backend"""
        if self._backend is None:
            if self.use_rust:
                try:
                    from memlibrary import MemoryNode as RustMemoryNode
                    self._backend = RustMemoryBridge()
                except ImportError:
                    print("Warning: Rust memory backend not available, falling back to Python")
                    self._backend = PythonMemoryBridge()
            else:
                self._backend = PythonMemoryBridge()
        return self._backend
    
    def create_node(self, content: Any, tags: List[str] = None, 
                   node_type: str = "generic", metadata: Dict = None) -> 'MemoryNode':
        """Create a new memory node with optional persistence"""
        memory_node = self.backend.create_node(content, tags or [], node_type, metadata or {})
        
        # Persist to database if persistence layer is available
        if self._persistence:
            self._persistence.save_memory_node(memory_node)
            
        return memory_node
    
    def find_by_tag(self, tag: str, limit: int = 100) -> List['MemoryNode']:
        """Find memory nodes by tag with database fallback"""
        results = self.backend.find_by_tag(tag, limit)
        
        # If backend returns few results and we have persistence, try database
        if len(results) < limit and self._persistence:
            db_results = self._persistence.find_by_tags([tag], limit - len(results))
            # Merge results, avoiding duplicates
            existing_ids = {node.id for node in results}
            for db_node in db_results:
                if db_node.id not in existing_ids:
                    results.append(db_node)
                    existing_ids.add(db_node.id)
                    
        return results
    
    def link_nodes(self, source_id: str, target_id: str, link_type: str = "related") -> bool:
        """Create a link between two memory nodes"""
        success = self.backend.link_nodes(source_id, target_id, link_type)
        
        # Also persist the link in database
        if success and self._persistence:
            self._persistence.create_link(source_id, target_id, link_type)
            
        return success
    
    def get_node(self, node_id: str) -> Optional['MemoryNode']:
        """Get memory node by ID with database fallback"""
        node = self.backend.get_node(node_id)
        
        if node is None and self._persistence:
            node = self._persistence.load_memory_node(node_id)
            
        return node

class RustMemoryBridge:
    """Wrapper for Rust memory operations"""
    
    def create_node(self, content: Any, tags: List[str], node_type: str, metadata: Dict) -> 'MemoryNode':
        from memlibrary import MemoryNode
        return MemoryNode(str(content), tags, node_type, metadata)
    
    def find_by_tag(self, tag: str, limit: int) -> List['MemoryNode']:
        from memlibrary import find_nodes_by_tag
        return find_nodes_by_tag(tag, limit)
    
    def link_nodes(self, source_id: str, target_id: str, link_type: str) -> bool:
        from memlibrary import create_link
        return create_link(source_id, target_id, link_type)
    
    def get_node(self, node_id: str) -> Optional['MemoryNode']:
        from memlibrary import get_node_by_id
        return get_node_by_id(node_id)

class PythonMemoryBridge:
    """Pure Python implementation of memory operations"""
    
    def create_node(self, content: Any, tags: List[str], node_type: str, metadata: Dict) -> 'MemoryNode':
        from bridge import MemoryNode
        return MemoryNode(content, tags, node_type, metadata)
    
    def find_by_tag(self, tag: str, limit: int) -> List['MemoryNode']:
        from bridge import MemoryTrace
        return MemoryTrace.find_by_tag(tag, limit)
    
    def link_nodes(self, source_id: str, target_id: str, link_type: str) -> bool:
        from bridge import MemoryNode
        source = MemoryNode.get_by_id(source_id)
        target = MemoryNode.get_by_id(target_id)
        if source and target:
            source.link(target, link_type)
            return True
        return False
    
    def get_node(self, node_id: str) -> Optional['MemoryNode']:
        from bridge import MemoryNode
        return MemoryNode.get_by_id(node_id)