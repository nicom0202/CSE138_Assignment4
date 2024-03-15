# CSE138_Assignment4

# Acknowledgements
    (1) Animesh Tiwary - We consulted on how to hash a key and map it to a shard group. He told us to use the hashlib library. 

# Citations 
    NOTE: We used (1) and (2) for ```get_shard_number(replica)``` & ```get_key_shard_desination(key)```.
    (1) Python Hashlib Library Docs - https://docs.python.org/3/library/hashlib.html
    (2) ChatGPT:
        Question: how do I hash a key in python using hashlib library?
        Answer: 
                To hash a key in Python using the hashlib library, you typically follow these steps:

                Import the hashlib library.
                Create a hash object using a specific hashing algorithm.
                Update the hash object with the bytes of the key.
                Retrieve the hexadecimal digest of the hash.
                Here's a basic example using the MD5 hashing algorithm:

                python
                Copy code
                import hashlib

                key = "my_key"
                hashed_key = int(hashlib.md5(key.encode()).hexdigest(), 16)

                print("MD5 Hashed key:", hashed_key)
                In this example:

                hashlib.md5() creates a hash object using the MD5 hashing algorithm.
                .encode() converts the string key to bytes because hashlib functions require bytes input.
                .hexdigest() retrieves the hexadecimal digest of the hash.
                You can replace md5 with other algorithms like sha256, sha1, etc., depending on your requirements.

# Team Contributions
(1) Nicolas Martinez:
                    (i)    ```/shard/key-count/<ID>```
                    (ii)   ```/shard/add-member/<ID>```
                    (iii)  ```/shard/reshard```
(2) Matthew Rico:
                    (i)   Making shard groups on startup & hash functions
                    (ii)  ```/shard/ids```
                    (iii) ```/shard/node-shard-id```
                    (vi)  ```/shard/members/<ID>```

## Mechanism Description

### (1) Tracking Causal Dependencies:
We decided to implement a vector clock solution using python dictionaries, storing the ip address of the replica as the key and the event counter as the value.
For each PUT/GET/DELETE request sent to a replica, we first check whether the request came from a client or another replica:
  1. If the request came from a client, the replica will have a check specfically for clients. In our ```dependency_test_client```, the replica checks if the causal-metadata is null. If it is, then the write does not depend on any other event, so it continues with the request. Otherwise, we compare the local vector clock with the vector clock that was supplied by the client. If any of the entries in the local vector clock is less than the entries in the supplied VC, then some dependcies have not been met so respond to the client with a 503 error. Otherwise, continue with the request.
It inserts the value into its store and merges and updates it vector clock, according to the algorithm discussed in lecture. After, the replica broadcasts the event to all other replicas, allowing them to contain a copy of the KVS store. Finally, respond to the client with 200 or 201 success code.
  2. If the request came from a replica, it will  perfom a check specifically for replicas. ```dependency_test_replica``` ensures that the entries in the sender's VC is only 1 unit of ahead of the local VC. It will then make sure that the sender's VC knows same amount of writes than the local VC. If these conditions are met, then replica will continue with the request. The replica will write the value to it's key value store. It will then merge it local VC with that of the senders. In this case, the replica will NOT broadcast to the other replicas. Finally, respond to the client with 200 or 201 success code.

### (2) Down Replica Detection:
When a replica receives a PUT/DELETE request from a client or a forwarding replica, it will write to the key value store and broadcast the change to all other replicas in it's shard using the ```broadcast_kvs``` function. If the requesting replica receives a Network Connection Error from any of the shard group members (indicating that they are down), it will append them to a list we called ```down_replicas```. After all shard group members have been contacted, if any replicas were added to ```down_replicas```, the requesting replica will call another a function we implemented called ```broadcast_view``` that alerts all other live replicas of the downed replica.

### (3) Key-to-Shard Mapping Mechanism:
Our approach to mapping a key to a shard group was in our ```get_key_shard_desination(key)``` function. It does the following:

            def get_key_shard_desination(key):
                global shard_count
                key_hash = int(hashlib.md5(key.encode()).hexdigest(), 16)
                return hash(key_hash) % shard_count



### (4) Approach to Divide Nodes into Shards
On startup or when a replica broadcasts their view, all replicas will hold a ```view_list``` that contain everyone's socket-addresses. Everyone will then sort these views using ```view_list.sort()```.
Now that everyone has the same ```view_list``` order, we then call a function called ```make_shard_groups()``` that does the following:

            def make_shard_groups():
                # Get globals
                global shard_count, view_list

                # Make a local shard_groups
                shard_groups = {}

                # Iterate over view list and assign shard groupings using modulas
                for replica_address in view_list:
                    shard_index = view_list.index(replica_address) % shard_count
                    if shard_index not in shard_groups:
                        shard_groups[shard_index] = []
                    shard_groups[shard_index].append(replica_address)

We use a dictionary that holds a shard ID (aka integers from zero to shard-count) to hold lists of replica addresses. Each list represents a shard group.

    return shard_groups
### (5) Resharding Mechanism