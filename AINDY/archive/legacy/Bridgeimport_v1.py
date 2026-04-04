from memory_bridge_rs import MemoryNode, MemoryTrace

root = MemoryNode("This came from Rust", "Archive", ["solon", "weave"])
child = MemoryNode("Linked from Rust layer", None, ["continuity"])
root.link(child)

trace = MemoryTrace()
trace.add_node(root)

for node in trace.find_by_tag("weave"):
    print(node["content"])
