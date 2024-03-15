# CSE138_Assignment4

# Acknowledgements
1. Animesh Tiwary - We consulted on how to hash a key and map it to a shard group. He told us to use the hashlib library. 

# Citations 
NOTE: We used (1) and (2) for ```get_shard_number(replica)``` & ```get_key_shard_desination(key)```.
1. Python Hashlib Library Docs - https://docs.python.org/3/library/hashlib.html
2. ChatGPT:
    - **Question**: how do I hash a key in python using hashlib library?
    - **Answer**: 

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
1. Nicolas Martinez:
    - **(i)**    ```/shard/key-count/<ID>```
    - **(ii)**   ```/shard/add-member/<ID>```
    - **(iii)**  ```/shard/reshard```
2. Matthew Rico:
    - **(i)**   Making shard groups on startup & hash functions
    - **(ii)**  ```/shard/ids```
    - **(iii)** ```/shard/node-shard-id```
    - **(vi)**  ```/shard/members/<ID>```

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

1. ``Data structures used``:
    No data structures were used.

2. ``Algorithms used``:
    We used the hashlib MD5 Hash function that accepts a sequence of bytes and returns a 128 bit hash value. We also used ```.encode()``` to convert the string into bytes to be acceptable by hash function & ```.hexdigest()``` to return the encoded data in hexadecimal format. The ```int(..., 16)``` converts the hexidecimal string from ```.hexdigest()``` into an integer. Finally we use ```% shard-count``` to map this integer to one of the shard IDs.

3. ``Rationale``:
    The rationale of doing this was to avoid using a Consistent Hashing approach because of the complexity of Consistent Hashing. The main reason for our simplier approach is to avoid having to remap keys when a replica goes down in Consistent Hashing. Using this method will always ensure that a key:value pair will get mapped to the same shard-group even if a replica goes down. Although more key:value pairs will have to be moved in a reshard, this approach allows us not to move key:value pairs everytime a replica goes down.

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
                
                return shard_groups

We use a dictionary that holds a shard ID (aka integers from zero to shard-count) to hold lists of replica addresses. Each list represents a shard group.

### (5) Resharding Mechanism
1. ``Logic of Implementation``:
    - **(i)** A client will request a reshard to a replica, this replica will be known as the ``leader`` of the reshard process.
    - **(ii)** The ``leader`` will check if that reshard is possible. 
    - **(iii)** If the reshard is possible, the ``leader`` will then create the new shard-groups & call a function ``start_reshard()``
    - **(vi)** The ``leader`` will then request each kvs portion & vector from each shard-group using a new endpoint called ```@app.route('/get-kvs-vc', methods=['GET'])``
    - **(v)** The ``leader`` now contains the entire kvs, it then splits the kvs store into the new shard-cout. I hold this data by using a dictionary that holds dictionaries. Each key to a dictionary represents a shard group ID and the dictionary is the respective kvs portion that shard group will hold. The ``leader`` also merges all vector clocks so that it holds the casual history of all the shard groups.
    - **(iv)** Finally the leader will send the new key value store portion, new vector clock, new shard-groups, & new shard-count to each replica respectively to an endpoint called ```@app.route('/reshard-sheep', methods=['PUT'])```
    - **(iiv)** When a replica who is not the leader (we call these replicas ``sheep``), will unconditionally accept the new key value store, vector clock, shard-groups & shard-count. At this point every replica will be in new shard-groups, have a new shard-count & have the same vector clocks.

2. ``Data structures used``:
    - **(i)** Dictionary of lists to hold shard-groups
    - **(ii)** Dictionary of dictionaries to holds partitioned key value store
    - **(iii)** Dictionary for vector clocks

3. ``Algorithms used``:
    - **(i)** For-loops to get the entire key value store & partition it.

4. ``Rationale``:
    - **(i)** Although this is probably not the most effient way to do this, we were having trouble having everyone be a ``leader`` and have this be decentralized algorithm but we ran into a lot of issues. The biggest issue was the redistribution of keys. So instead we decided on a centralized approach and just have one replica organize the reshard.