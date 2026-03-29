mod cpp_bridge;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use chrono::Utc;

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

    fn to_dict(&self, py: Python) -> PyObject {
        let dict = PyDict::new(py);

        dict.set_item("id", &self.id).unwrap();
        dict.set_item("timestamp", &self.timestamp).unwrap();
        dict.set_item("content", &self.content).unwrap();
        dict.set_item("source", &self.source).unwrap();
        dict.set_item("tags", &self.tags).unwrap();

        // 🔥 Convert children recursively
        let py_children: Vec<PyObject> = self
            .children
            .iter()
            .map(|child| child.to_dict(py))
            .collect();

        dict.set_item("children", py_children).unwrap();

        dict.into()
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

    fn export(&self, py: Python) -> Vec<PyObject> {
        self.root_nodes
            .iter()
            .map(|node| node.to_dict(py))
            .collect()
    }

    fn find_by_tag(&self, py: Python, tag: String) -> Vec<PyObject> {
        fn recursive_find(
            node: &MemoryNode,
            tag: &str,
            py: Python,
            acc: &mut Vec<PyObject>,
        ) {
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

/// Compute cosine similarity between two equal-length float vectors.
/// Calls the C++ kernel via Rust FFI for maximum performance.
/// Used by the Infinity Algorithm for semantic memory node scoring.
///
/// Returns a value in [-1.0, 1.0]:
///   1.0 = identical direction, 0.0 = orthogonal, -1.0 = opposite
#[pyfunction]
fn semantic_similarity(a: Vec<f64>, b: Vec<f64>) -> PyResult<f64> {
    if a.len() != b.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Vectors must be same length: {} != {}",
            a.len(),
            b.len()
        )));
    }
    Ok(cpp_bridge::compute_similarity(&a, &b))
}

/// Compute weighted dot product of two equal-length float vectors.
/// Calls the C++ kernel via Rust FFI.
///
/// Maps directly to the Infinity Algorithm engagement score numerator:
///   values  = [likes, shares, comments, clicks, time_on_page]
///   weights = [2.0,   3.0,    1.5,     1.0,    0.5]
///   result  = weighted_dot_product(values, weights) / total_views
#[pyfunction]
fn weighted_dot_product(values: Vec<f64>, weights: Vec<f64>) -> PyResult<f64> {
    if values.len() != weights.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Vectors must be same length: {} != {}",
            values.len(),
            weights.len()
        )));
    }
    Ok(cpp_bridge::compute_weighted_dot(&values, &weights))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn score_memory_nodes(
    similarities: Vec<f64>,
    recencies: Vec<f64>,
    success_rates: Vec<f64>,
    usage_frequencies: Vec<f64>,
    graph_bonuses: Vec<f64>,
    impact_scores: Vec<f64>,
    trace_bonuses: Vec<f64>,
    low_value_flags: Vec<bool>,
) -> PyResult<Vec<f64>> {
    let len = similarities.len();
    let lengths = [
        recencies.len(),
        success_rates.len(),
        usage_frequencies.len(),
        graph_bonuses.len(),
        impact_scores.len(),
        trace_bonuses.len(),
        low_value_flags.len(),
    ];
    if lengths.iter().any(|candidate_len| *candidate_len != len) {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "All score vectors must be the same length",
        ));
    }

    let mut scores = Vec::with_capacity(len);
    for idx in 0..len {
        let usage = usage_frequencies[idx];
        let success_weight = if usage > 5.0 { 0.25 } else { 0.20 };
        let impact_bonus = (impact_scores[idx] / 5.0).clamp(0.0, 1.0) * 0.15;
        let normalized_usage = normalize_usage(usage);

        let mut score = similarities[idx] * 0.40
            + recencies[idx] * 0.15
            + success_rates[idx] * success_weight
            + normalized_usage * 0.10
            + graph_bonuses[idx] * 0.15
            + impact_bonus
            + trace_bonuses[idx];

        if low_value_flags[idx] {
            score *= 0.5;
        }
        scores.push(score);
    }

    Ok(scores)
}

fn normalize_usage(value: f64) -> f64 {
    if value <= 0.0 {
        return 0.0;
    }
    let numerator = (1.0 + value).ln();
    let denominator = 101.0_f64.ln();
    if denominator.abs() < f64::EPSILON {
        return 0.0;
    }
    (numerator / denominator).clamp(0.0, 1.0)
}

#[pymodule]
fn memory_bridge_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<MemoryNode>()?;
    m.add_class::<MemoryTrace>()?;
    m.add_function(wrap_pyfunction!(semantic_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(weighted_dot_product, m)?)?;
    m.add_function(wrap_pyfunction!(score_memory_nodes, m)?)?;
    Ok(())
}
