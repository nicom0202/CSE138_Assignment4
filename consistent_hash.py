import hashlib

class ConsistentHashRing:
    def __init__(self, view_list=None):
        self.nodes = {}
        self.sorted_keys = []

        if view_list:
            self.init_nodes(view_list)

    def hash(self, value):
        return int(hashlib.md5(value.encode()).hexdigest(), 16) % 360

    def init_nodes(self, view_list, num_virtual_nodes=10):
        for node in view_list:
            for i in range(num_virtual_nodes):
                virtual_node = f"{node}_virtual_{i}"
                hash_val = self.hash(virtual_node)
                self.nodes[hash_val] = node
                self.sorted_keys.append(hash_val)
        self.sorted_keys.sort()

    def find_nearest_node(self, key_hash):
        if not self.nodes:
            return None

        for node_hash in self.sorted_keys:
            if node_hash >= key_hash:
                return self.nodes[node_hash]
        # Wrap around to the first node if not found
        return self.nodes[self.sorted_keys[0]]

    def add_node(self, node):
        hash_val = self.hash(node)
        self.nodes[hash_val] = node
        self.sorted_keys.append(hash_val)
        self.sorted_keys.sort()

    def remove_node(self, node):
        hash_vals_to_remove = []
        for hash_val, value in self.nodes.items():
            if value.startswith(node):
                hash_vals_to_remove.append(hash_val)
        for hash_val in hash_vals_to_remove:
            del self.nodes[hash_val]
            self.sorted_keys.remove(hash_val)

    # method to see what node a specific key will get hashed to
    def hash_key_to_node(self, key):
        key_hash = self.hash(key)
        return self.find_nearest_node(key_hash)

    def __str__(self):
        return "\n".join([f"{self.nodes[key]}: {key}" for key in self.sorted_keys])


# test_key = 'p'

# # Usage example
# view_list = ['10.10.0.2:8090', '10.10.0.3:8090', '10.10.0.4:8090', '10.10.0.5:8090', '10.10.0.6:8090', '10.10.0.7:8090']
# hash_ring = ConsistentHashRing(view_list)
# # print(f"Hash-ring:")
# # print(hash_ring)

# # Test hash_key_to_node method
# key = test_key
# node = hash_ring.hash_key_to_node(key)
# print(f"Hash-ring on start-up:")
# print(f"\nThe key '{key}' will be hashed to node: {node}")

# # Add a new node
# hash_ring.add_node('10.10.0.8:8090')

# # # Print the hash ring after a new node
# # print("\nHash-ring after adding 10.10.0.8:8090:")
# # print(hash_ring)

# # Test hash_key_to_node method
# key = test_key
# node = hash_ring.hash_key_to_node(key)
# print(f"Hash-ring after adding 10.10.0.8:8090:")
# print(f"\nThe key '{key}' will be hashed to node: {node}")

# # Remove a node
# hash_ring.remove_node('10.10.0.2:8090')

# # # Print the hash ring after removing a node
# # print("\nHash-ring after removing 10.10.0.2:8090:")
# # print(hash_ring)

# # Test hash_key_to_node method
# key = test_key
# node = hash_ring.hash_key_to_node(key)
# print(f"Hash-ring after removing 10.10.0.2:8090:")
# print(f"\nThe key '{key}' will be hashed to node: {node}")








































# '''
# # Add virtual nodes for better distribution
# def init_nodes(self, view_list, num_virtual_nodes=10):
#     for node in view_list:
#         for i in range(num_virtual_nodes):
#             virtual_node = f"{node}_virtual_{i}"
#             hash_val = self.hash(virtual_node)
#             self.nodes[hash_val] = node
#             self.sorted_keys.append(hash_val)
#     self.sorted_keys.sort()
# '''

# '''
# # Original node distribution
# def init_nodes(self, view_list):
#     for node in view_list:
#         hash_val = self.hash(node)
#         self.nodes[hash_val] = node
#         self.sorted_keys.append(hash_val)
#     self.sorted_keys.sort()
# '''
# '''
# # Original remove node
# def remove_node(self, node):
#     hash_val = self.hash(node)
#     if hash_val in self.nodes:
#         del self.nodes[hash_val]
#         self.sorted_keys.remove(hash_val)
# '''