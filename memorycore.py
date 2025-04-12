// memory_bridge_core.rs
// Memory Bridge v0.1 - Rust Layer | Solon Protocol Anchor

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// A single unit of symbolic memory
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryNode {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub content: String,
    pub source: Option<String>,
    pub tags: Vec<String>,
    pub children: Vec<MemoryNode>,
}

impl MemoryNode {
    pub fn new(content: &str, source: Option<&str>, tags: Vec<&str>) -> Self {
        MemoryNode {
            id: Uuid::new_v4().to_string(),
            timestamp: Utc::now(),
            content: content.to_string(),
            source: source.map(|s| s.to_string()),
            tags: tags.iter().map(|s| s.to_string()).collect(),
            children: vec![],
        }
    }

    pub fn link(&mut self, child: MemoryNode) {
        self.children.push(child);
    }
}

/// A trace structure for storing memory nodes
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct MemoryTrace {
    pub root_nodes: Vec<MemoryNode>,
}

impl MemoryTrace {
    pub fn new() -> Self {
        Self { root_nodes: vec![] }
    }

    pub fn add_node(&mut self, node: MemoryNode) {
        self.root_nodes.push(node);
    }

    pub fn find_by_tag(&self, tag: &str) -> Vec<&MemoryNode> {
        let mut matches = Vec::new();
        for node in &self.root_nodes {
            matches.extend(recursive_find(node, tag));
        }
        matches
    }
}

/// Recursively search for tagged nodes
fn recursive_find<'a>(node: &'a MemoryNode, tag: &str) -> Vec<&'a MemoryNode> {
    let mut matches = Vec::new();
    if node.tags.contains(&tag.to_string()) {
        matches.push(node);
    }
    for child in &node.children {
        matches.extend(recursive_find(child, tag));
    }
    matches
}
