// lib.rs
use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use chrono::{Utc, DateTime};

#[pyclass]
#[derive(Clone, Serialize, Deserialize)]
pub struct MemoryNode {
    #[pyo3(get)]
    pub id: String,
    #[pyo3(get)]
    pub timestamp: String,
    #[pyo3(get, set)]
    pub content: String,
    #[pyo3(get, set)]
    pub source: Option<String>,
    #[pyo3(get, set)]
    pub tags: Vec<String>,
    #[pyo3(get)]
    pub children: Vec<MemoryNode>,
}

#[pymethods]
impl MemoryNode {
    #[new]
    fn new(content: String, source: Option<String>, tags: Vec<String>) -> Self {
        MemoryNode {
            id: Uuid::new_v4().to_string(),
            timestamp: Utc::now().to_rfc3339(),
            content,
            source,
            tags,
            children: vec![],
        }
    }

    fn link(&mut self, child: MemoryNode) {
        self.children.push(child);
    }

    fn to_dict<'py>(&self, py: Python<'py>) -> &'py PyDict {
        let dict = PyDict::new(py);
        dict.set_item("id", &self.id).unwrap();
        dict.set_item("timestamp", &self.timestamp).unwrap();
        dict.set_item("content", &self.content).unwrap();
        dict.set_item("source", &self.source).unwrap();
        dict.set_item("tags", &self.tags).unwrap();
        dict.set_item("children", &self.children).unwrap();
        dict
    }
}

#[pyclass]
pub struct MemoryTrace {
    pub root_nodes: Vec<MemoryNode>,
}

#[pymethods]
impl MemoryTrace {
    #[new]
    fn new() -> Self {
        Self { root_nodes: vec![] }
    }

    fn add_node(&mut self, node: MemoryNode) {
        self.root_nodes.push(node);
    }

    fn export<'py>(&self, py: Python<'py>) -> Vec<&'py PyDict> {
        self.root_nodes.iter().map(|node| node.to_dict(py)).collect()
    }

    fn find_by_tag<'py>(&self, py: Python<'py>, tag: String) -> Vec<&'py PyDict> {
        fn recursive_find<'a>(node: &'a MemoryNode, tag: &str, py: Python<'a>, acc: &mut Vec<&'a PyDict>) {
            if node.tags.contains(&tag.to_string()) {
                acc.push(node.to_dict(py));
            }
            for child in &node.children {
                recursive_find(child, tag, py, acc);
            }
        }

        let mut results = vec![];
        for node in &self.root_nodes {
            recursive_find(node, &tag, py, &mut results);
        }
        results
    }
}

#[pymodule]
fn memory_bridge_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<MemoryNode>()?;
    m.add_class::<MemoryTrace>()?;
    Ok(())
}
