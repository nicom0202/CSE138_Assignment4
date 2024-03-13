import hashlib

class ConsistentHashRing:
    def __init__(self, view_list=None):
        self.nodes = {}
        self.node_hash_value = []

        if view_list:
            self.init_nodes(view_list)

    def init_nodes(self, view_list, num_virtual_nodes=5):
        for node in view_list:
            for i in range(num_virtual_nodes):
                virtual_node = f"{node}_virtual_{i}"
                hash_val = self.hash(virtual_node)
                self.nodes[hash_val] = node
                self.node_hash_value.append(hash_val)
        self.node_hash_value.sort()
    
    def hash(self, value):
        return int(hashlib.md5(value.encode()).hexdigest(), 16) % 10000000

    def find_nearest_node(self, key_hash):
        if not self.nodes:
            return None

        for node_hash in self.node_hash_value:
            if node_hash >= key_hash:
                return self.nodes[node_hash]
        # Wrap around to the first node if not found
        return self.nodes[self.node_hash_value[0]]

    def add_node(self, node):
        hash_val = self.hash(node)
        self.nodes[hash_val] = node
        self.node_hash_value.append(hash_val)
        self.node_hash_value.sort()

    def remove_node(self, node):
        hash_vals_to_remove = []
        for hash_val, value in self.nodes.items():
            if value.startswith(node):
                hash_vals_to_remove.append(hash_val)
        for hash_val in hash_vals_to_remove:
            del self.nodes[hash_val]
            self.node_hash_value.remove(hash_val)

    # Function to see what node a specific key will get hashed to
    def hash_key_to_node(self, key):
        key_hash = self.hash(key)
        return self.find_nearest_node(key_hash)

    def __str__(self):
        return "\n".join([f"{self.nodes[key]}: {key}" for key in self.node_hash_value])

