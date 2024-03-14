from flask import Flask, make_response, jsonify, request
import requests
import hashlib
import os
import time
import math

app = Flask(__name__)

# TODO: when a replica goes down, we need to redistribute keys
# NOTE: get rid of consistent hashing bc you wont have to redistrbibute keys when a replica dies


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
# INITIALIZE GLOABLS:                       SHARD_GROUPS
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This function will assign replicas to a shard group
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

# This function will get the shard number for a replica
def get_shard_number(replica):
    global view_list, shard_count
    return view_list.index(replica) % shard_count 

# This function will find the shard group that a key will be assigned to
def get_key_shard_desination(key):
    global shard_count
    key_hash = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return hash(key_hash) % shard_count


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
# HELPER FUNCTIONS:                   BROADCASTING UPDATES TO VIEW
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This function will broadcast a view update to everyone in the view_list
def broadcast_view(method, replica_address):
    # Get gloabls
    global view_list, my_socket_address

    # Broadcast to everyone 
    for replica in view_list[:]:
        if replica != my_socket_address:
                try:
                    data = {'socket-address': replica_address}
                    url = f"http://{replica}/view"
                    if method == 'PUT':
                        requests.put(url, json=data, timeout=1)
                    elif method == 'DELETE':
                        requests.delete(url, json=data, timeout=5)
                    else:
                        return make_response(jsonify({'error': 'Server error'}), 500)
                except requests.exceptions.RequestException as e:
                    # No need to delete/broadcast replica bc it will eventually get detected kvs broadcast
                    print(f"Exception caught in broadcast_view() to {replica}: {e}")


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /view endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This endpoint handles all view operations
@app.route('/view', methods=['PUT','GET','DELETE'])
def view():
    # Get globals
    global view_list

    # ----- GET logic ------
    # Check if it's a GET request
    if request.method == 'GET':
        return make_response(jsonify({"view": view_list}), 200)
    
    # Get data from request
    data = request.get_json(silent=True)

    # Check if data is None or empty
    if data is None:
        return make_response(jsonify({'error': 'Bad request, empty data'}), 400)
    
    # Check if socket-address is in data
    if 'socket-address' not in data:
        return make_response(jsonify({'error': 'Bad request, missing socket-address'}), 400)
    socket_address = data.get('socket-address')

    # Check that socket-address is not None
    if socket_address is None:
        return make_response(jsonify({'error': 'Bad request, missing socket-address'}), 400)

    # ----- PUT logic ------
    if request.method == 'PUT':
        # Check if the socket already exists in their view
        if socket_address in view_list:
            return make_response(jsonify({"result": "already present"}), 200)


        # Add new replica to view list
        if socket_address not in view_list:
            view_list.append(socket_address)
            view_list.sort()

        # Add new replica address in vector clock
        if socket_address not in vector_clock:
            vector_clock[socket_address] = 0

        # Make response
        return make_response(jsonify(data={"result": "added"}), 201)
    
    # ----- DELETE logic ------
    elif request.method == 'DELETE':
        # Check if socket-address exists in the data
        if socket_address is None:
            return make_response(jsonify({'error': 'Bad request, missing socket-address'}), 400)

        # Check if socket-address exists in your view
        if socket_address in view_list and socket_address != my_socket_address:
            view_list.remove(socket_address)
            hash_ring.remove_node(socket_address)
            return make_response(jsonify({"result": "deleted"}), 200)
    else:
        make_response(jsonify({'error': 'Server error'}), 500)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
# HELPER FUNCTIONS:                  VECTOR CLOCKS COMPARISON     
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This function will update the replicas current position by 1
def update_vector_clock():
    # Get globals
    global vector_clock
    # Update your socket address in vector clock
    vector_clock[my_socket_address] += 1

# This function will do preform a dependency test for a client NOTE: VC2 is the vector_clock of the requesting client
def dependency_test_client(VC2): 
    # Get globals
    global vector_clock, shard_groups, shard_number
    VC1 = vector_clock.copy()

    # check if VC2 is empty
    if VC2 is None:
        return True
    # Only compare addresses in view list (NOTE: We're not deleting vc info on replicas that are down)
    for address in shard_groups[shard_number][:]:
        if address in VC2:
            if VC1[address] < VC2[address]:
                return False
    
    return True

# This function will do preform a dependency test for a client NOTE: VC2 is the vector_clock of the requesting replica and sender is the requesting replica socket-address
def dependency_test_replica(VC2, sender): 
    # Get global
    global vector_clock, view_list
    VC1 = vector_clock.copy()

    # Check that the sender vc is only 1 ahead of your vc
    if VC2[sender] != VC1[sender] + 1:
        return False
    
    # Check that the sender vc knows the same amount of writes as you
    for key in shard_groups[shard_number][:]:
        if key in VC2:
            if key != sender and VC2[key] > VC1[key]:
                return False
    return True

# This function will merge the vector clocks using point-wise maximum technique 
def merge_vector_clocks(VC2):
    # Get globals
    global vector_clock
    
    # If VC2 is none, then it's the first time a client requested a write, no need to merge 
    if VC2 is not None:
        merged_vc = {}

        # Merge keys from both vector clocks
        all_keys = set(vector_clock.keys()).union(set(VC2.keys()))

        # Iterate over all keys
        for key in all_keys:
            # Get values for the key from both vector clocks
            value1 = vector_clock.get(key, 0)
            value2 = VC2.get(key, 0)

            # Use point-wise maximum to merge values
            merged_vc[key] = max(value1, value2)

        vector_clock.clear()
        vector_clock = merged_vc


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
# HELPER FUNCTIONS:            BROADCASTING KVS UPDATES WITHIN SHARD GROUPS
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This function will broadcast a kvs update to everyone in the shard-group
def broadcast_kvs(method, key, value=None):
    # Get globals
    global shard_groups, my_socket_address, shard_number

    # Create a list to hold replicas that are down
    down_replicas = []

    # Broadcast to everyone in shard group (skip yourself), to PUT/DELETE a key in kvs
    for replica in shard_groups[shard_number][:]:
        if replica != my_socket_address:
            while True:
                try:
                    # Create request
                    url = f"http://{replica}/kvs/{key}"

                    # Create data
                    if method == 'PUT':
                        data = {'value': value, 'causal-metadata': vector_clock}
                    else: # method == DELETE
                        data = {'causal-metadata': vector_clock}

                    # Create header
                    headers = {'Replica': my_socket_address}

                    # Make request
                    response = requests.put(url, json=data, headers=headers,timeout=5)

                    # Dependencies are NOT met, sleep and try again
                    if response.status_code == 503:
                        time.sleep(1)
                        continue
                    # Dependencies ARE met, break the while loop & continue the for-loop
                    elif response.status_code == 200 or response.status_code == 201 or response.status_code == 404:
                        break
                    # Unexpected behavior 
                    else:
                        # raise Exception
                        raise Exception
                except requests.exceptions.RequestException:
                    # Found down replica, delete from view list & add to down_replicas
                    down_replicas.append(replica)
                    break  # Continue to for loop iteration and break while loop iteration(aka next replica)
   
    # If you find any replicas that are down & you're not alone, broadcast it  
    if len(down_replicas) > 0 and len(view_list) != 1:
        for replica in down_replicas:
            if replica != my_socket_address:
                broadcast_view('DELETE', replica)
    pass



# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                         /kvs/<key> endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This endpoint handles all kvs operations
@app.route('/kvs/<key>', methods=['PUT', 'GET','DELETE'])
def put_key_value(key):
    # Get data from json
    data = request.get_json(silent=True)

    # Check to see if data is empty
    if data is None:
        return make_response(jsonify({'error': 'data is none'}), 400)
    
    # Get method
    if request.method == 'PUT':
        method = 'PUT'
    elif request.method == 'GET':
        method = 'GET'
    elif request.method == 'DELETE':
        method = 'DELETE'
    else:
        return make_response(jsonify({'error': 'Server error'}), 500)

    # Process request
    return process_request(method, key, data)

# This function acts as the proxy/forwarder to the correct shard group
def handle_forwarded_request(method, key):
    # Make a response variable
    response = None

    # Find out what shard this key belongs to
    key_shard_destination = get_key_shard_desination(key)

    # Forward to 1 replica in shard group  (NOTE: only forward to 1 because they will broadcast to everyone in their group)
    for replica in shard_groups[key_shard_destination][:]:
        try:
            # Make a url to replica
            url = f"http://{replica}/kvs/{key}"
            # forward respective method and return response to client
            if method == 'GET':
                response = requests.get(url, json=request.get_json(silent=True))
            elif method == 'PUT':
                response = requests.put(url, json=request.get_json(silent=True))
            elif method == 'DELETE':
                response = requests.delete(url, json=request.get_json(silent=True))
            else:
                return make_response(jsonify({'error': 'Server error'}), 500)
            # break out of loop
            break
        except requests.exceptions.RequestException as e:
            # forwarding request failed & the shard-group will catch this error then tell everyone to delete this shard
            print(f'Forwarding request failed, could not connect to {replica}: {e}')
            continue
    
    return response.content, response.status_code, response.headers.items()

# This function handles the logic for kvs endpoint
def process_request(method, key, data=None):
    # Get global
    global key_value_store, vector_clock

    # Hash the key
    key_shard_destination = get_key_shard_desination(key)

    # Check if key belongs to my shard group
    if key_shard_destination != shard_number:
        return handle_forwarded_request(method, key)
    
    # Create a local status code variable 
    status_code = 0

    # Create a local boolean if its from a client or replica
    from_client = False

#          ~~~~~~~~~~~~~~~~~~~~~
#          ~~~~~ PUT logic ~~~~~
#          ~~~~~~~~~~~~~~~~~~~~~
    if method == 'PUT':
        # Check that value exists in data
        if 'value' not in data:
            return make_response(jsonify({'error': 'PUT request does not specify a value'}), 400)
        value = data.get('value')

        # Check that casaul meta data exists in json
        if 'causal-metadata' not in data:
            return make_response(jsonify({'error': 'PUT request does not contain causal-metadata'}), 400) 
        causal_metadata = data.get('causal-metadata')

        # Check header to see if request is from a client
        if 'Replica' not in request.headers:
            dependency = dependency_test_client(causal_metadata)
            from_client = True
        else: # From a replica
            dependency = dependency_test_replica(causal_metadata, request.headers.get('Replica'))

        if dependency:    
            # Check if key is to long
            if len(key) > 50:
                return make_response(jsonify({'error': 'Key is too long'}), 400)
            
            # Check if key exists or not in kvs
            if key in key_value_store:
                status_code = 200
            else:
                status_code = 201

            # Write to key value store
            key_value_store[key] = value

            # Merge vector clocks
            merge_vector_clocks(causal_metadata)

            # Update vector clock & broadcast to everyone if from client
            if from_client:
                update_vector_clock()
                broadcast_kvs('PUT', key, value)

            # Reuslt was replaced
            if status_code == 200:
                return make_response(jsonify({"result": "replaced", "causal-metadata": vector_clock}), 200)
            # Result was created
            return make_response(jsonify({"result": "created", "causal-metadata": vector_clock}), 201)
        else:
            return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)
        
#          ~~~~~~~~~~~~~~~~~~~~~
#          ~~~~~ GET logic ~~~~~
#          ~~~~~~~~~~~~~~~~~~~~~
    elif method == 'GET':
        # Now check that casaul meta data exists in json
        if 'causal-metadata' not in data:
            return make_response(jsonify({'error': 'GET request does not contain causal-metadata'}), 400) 
        causal_metadata = data.get('causal-metadata')

        # Check dependency test (only clients use this)
        dependency = dependency_test_client(causal_metadata)

        if dependency:
            # Merge the vector clocks
            merge_vector_clocks(causal_metadata)

            # Found key:value
            if key in key_value_store:
                return make_response(jsonify({"result": "found", "value": key_value_store[key], "causal-metadata": vector_clock}), 200)
            else: # Does not exist
                return make_response(jsonify({"error": "Key does not exist"}), 404)
            
        else: 
            # Dependencies are NOT met
            return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)
#          ~~~~~~~~~~~~~~~~~~~~~~
#          ~~~~ DELETE logic ~~~~
#          ~~~~~~~~~~~~~~~~~~~~~~
    elif method == 'DELETE':
        # Check that casaul meta data exists in json
        if 'causal-metadata' not in data:
            return make_response(jsonify({'error': 'DELETE request does not contain causal-metadata'}), 400) 
        causal_metadata = data.get('causal-metadata')

        # Check header to see if request is from a client
        if 'Replica' not in request.headers:
            dependency = dependency_test_client(causal_metadata)
            from_client = True
        else: # From a replica
            dependency = dependency_test_replica(causal_metadata, request.headers.get('Replica'))


        if dependency:
            # Check if key exists in the store
            if key not in key_value_store:
                return make_response(jsonify({"error": "Key does not exist"}), 404)
            
            # Delete key
            del key_value_store[key]

            # Merge vector clocks
            merge_vector_clocks(causal_metadata)
            
            # Update vector clock & broadcast to everyone if from client
            if from_client:
                update_vector_clock()
                broadcast_kvs('DELETE', key)
            return make_response(jsonify({"result": "deleted", "causal-metadata": vector_clock}), 200)
        else:
            return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                       /shard/ids endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This endpoint handles all shard/ids operations
@app.route('/shard/ids', methods=['GET'])
def get_shard_ids():
    # Get globals
    global shard_groups
    # Make response
    return make_response(jsonify({'shard-ids': list(shard_groups.keys())}), 200)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                     /shard/node-shard-id endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This endpoint handles all /shard/node-shard-id operations
@app.route('/shard/node-shard-id', methods=['GET'])
def get_node_shard_id():
    # Get globals
    global shard_number
    # Make respone
    return make_response(jsonify({'node-shard-id': shard_number}), 200)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                      /shard/members/<ID> endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This endpoint handles all /shard/members/<ID> operations
@app.route('/shard/members/<ID>', methods=['GET'])
def get_shard_members(ID):

    # Get globals
    global shard_groups

    try:
        # Attempt to convert ID to int
        ID = int(ID)

        # Check if ID is in shard_groups
        if ID in shard_groups:
            return make_response(jsonify({'shard-members': shard_groups.get(ID)}), 200)
        
        # ID does not exist in shard_groups
        return make_response(jsonify({'error': 'No such shard ID exists'}), 404)
    except ValueError:
        # Handle the case where ID cannot be converted to an integer
        return make_response(jsonify({'error': 'No such shard ID exists'}), 404)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                   /shard/key-count/<ID> endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================



@app.route('/shard/key-count/<ID>', methods=['GET'])
def get_key_count_at_ID(ID):

    # Get globals
    global key_value_store, shard_groups, view_list
    
    # Local variables
    response = None
    size = None
    down_replicas = []
    try:
        # Attempt to convert ID to int
        ID = int(ID)

    except ValueError:
        # Handle the case where ID cannot be converted to an integer
        return make_response(jsonify({'error': 'No such shard ID exists'}), 404)
    
    # Check that ID is a valid shard group
    if ID not in shard_groups:
        make_response(jsonify({'error': 'Shard ID does not exist'}), 404)

    # Check if ID is my shard group
    if ID == shard_number:
        return make_response(jsonify({'shard-key-count': len(key_value_store)}), 200)
    else: # Forward request to a replica in that shard group
            for replica in shard_groups[ID][:]:
                try:
                    # Make url
                    url = f"http://{replica}/key-count"

                    # If you get a response from a single replica, break the for-loop
                    response = requests.get(url, timeout=5)
                    
                    # Check that status code is 200
                    if response.status_code == 200:
                        # Get data from response 
                        data = response.json()

                        # Check that 'size' is in the respone
                        if data.get('size') is not None:
                            size = data.get('size')
                            break
                    else:
                        # Unexpected behavior from replica
                        continue
                except requests.exceptions.RequestException as e:
                    # Remove replica from view_list
                    view_list.remove(replica)

                    # Add replica to down_replicas
                    down_replicas.append(replica)
                    continue

    # Broadcast bad replicas
    if len(down_replicas) > 0:
        for replica in view_list:
            if replica != my_socket_address:
                broadcast_view('DELETE', replica)

    # Return response
    return make_response(jsonify({'shard-key-count': size}), 200)

@app.route('/key-count', methods=['GET'])
def get_key_value_store_size():
    # Get globals
    global key_value_store
    # Return size of key-value-store
    return make_response(jsonify({'size': len(key_value_store)}), 200)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                    /shard/add-member/<ID> endpoint                 
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


def broadcast_add_member(shard_id, socket_address):

    # Get globals
    global view_list, my_socket_address

    # Create a list to hold replicas that are down
    down_replicas = []

    # Broadcast to everyone in view list (skip yourself) to PUT /shard/add-member/<ID>
    for replica in view_list[:]:
        if replica != my_socket_address:
            try:
                data = {'socket-address': socket_address}
                url = f"http://{replica}/shard/add-member/{shard_id}"
                headers = {'Replica': my_socket_address}
                response = requests.put(url, json=data, headers=headers, timeout=5)
                if response.status_code == 200:
                    continue
                else:
                    # unexpected behavior TODO: maybe raise an exception?????
                    pass
            except requests.exceptions.RequestException as e:
                print(f"Unable to connect to {replica} ... error: {e}")
                down_replicas.append(replica)
    
    # Broadcast to everyone a replica is down
    if len(down_replicas) > 0:
        for replica in down_replicas:
            if replica != my_socket_address:
                broadcast_view('DELETE', replica)

@app.route('/shard/add-member/<ID>', methods=['PUT'])
def add_member(ID):

    # Get globals
    global view_list, shard_groups, key_value_store, vector_clock, shard_count, shard_groups, shard_number

    try:
        # Attempt to convert ID to int
        ID = int(ID)

    except ValueError:
        # Handle the case where ID cannot be converted to an integer
        return make_response(jsonify({'error': f'ID: {ID} does not exist in shard ids'}), 404)

    # Get the data from the request
    data = request.get_json()

    # Check that socket-address is not None
    if 'socket-address' not in data:
        return make_response(jsonify({'error': 'No socket-address sent'}), 400)
    
    # Get new socket-address
    new_socket_address = data.get('socket-address')

    # Check that ID is an existing shard group
    if ID not in shard_groups:
        return make_response(jsonify({'error': f'ID: {ID} does not exist in shard ids'}), 404)
    
    # Check if socket-address is in my view list
    if new_socket_address not in view_list:
        print(f"{new_socket_address} is not in my view_list: {view_list}")
        return make_response(jsonify({'error': f'{new_socket_address} does not exist in my view'}), 404)

    # Add new_socket_address to shard_groups[ID] IF it's not already there
    if new_socket_address not in shard_groups[ID]:
        shard_groups[ID].append(new_socket_address)
        print(f"Addinng {new_socket_address} to shard group {ID} ... shard_groups: {shard_groups}")

    # Check if this request is from a client
    if 'Replica' not in request.headers:
        # Broadcast to everyone to add this replica to shard_groups[ID]
        broadcast_add_member(ID, new_socket_address)

    # If ID is my shard group, send a PUT request to new_socket_address in /populate endpoint. Send KVS and VC
    if ID == shard_number and new_socket_address != my_socket_address:
        try:
            data = {'kvs': key_value_store, 'vc': vector_clock, 'shard-groups': shard_groups, 'shard-count': shard_count, 'shard-number':shard_number}
            url = f"http://{new_socket_address}/populate"
            headers = {'Replica': my_socket_address}
            response = requests.put(url, json=data, headers=headers, timeout=5)
            if response.status_code != 200:
                # Unexpected behavior TODO: maybe raise exception 
                pass
        except requests.exceptions.RequestException as e:
            print(f"Unable to connect to {new_socket_address} when sending a /populate request: {e}")
            #TODO: do i need to delete this view????


    # Make a response
    return make_response(jsonify({'result': 'node added to shard'}), 200)

@app.route('/populate', methods=['PUT'])
def populate():
    # if you get this route it means you're new and need the info for your shard group to participate
    # NOTE: will need to send: shard-id, kvs & vc

    # Get globals
    global key_value_store, vector_clock, shard_groups, shard_count, shard_number

    # Get data from request
    data = request.get_json()

    # Check that kvs is in data
    if 'kvs' not in data:
        make_response(jsonify({'error': 'Missing kvs in /populate route'}), 400)

    # Update kvs
    key_value_store = data.get('kvs')

    # Check that vc is in data
    if 'vc' not in data:
        make_response(jsonify({'error': 'Missing vc in /populate route'}), 400)

    # Update vc
    vector_clock = data.get('vc')

    # Check that shard-groups is in data
    if 'shard-groups' not in data:
        make_response(jsonify({'error': 'Missing shard-groups in /populate route'}), 400)

    # Update shard_groups
    shard_groups = data.get('shard-groups')

    # Check that shard-count is in data
    if 'shard-count' not in data:
        make_response(jsonify({'error': 'Missing shard-count in /populate route'}), 400)

    # Update shard_count
    shard_count = data.get('shard-count')

    # Check that shard-number is in data
    if 'shard-number' not in data:
        make_response(jsonify({'error': 'Missing shard-count in /populate route'}), 400)

    # Update shard_number
    shard_number = data.get('shard-number')

    # Make response 
    print(f"Updated kvs, vc, shard-count, and shard-groups from {request.headers.get('Replica')}")
    return make_response(jsonify({'result': f"Updated kvs & vc from {data.get('Replica')}"}))


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                            /shard/reshard endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


@app.route('/shard/reshard', methods=['PUT'])
def reshard():
    print(f"Made it to reshard, leader")
    # Get globals
    global view_list

    # Get data
    data = request.get_json()

    # Check to see if data is correct
    if data is None:
        return make_response(jsonify({'error': 'data is none'}), 400)
    
    # Check that casaul meta data exists in json
    if 'shard-count' not in data:
        return make_response(jsonify({'error': 'PUT request does not contain shard-count'}), 400) 

    new_shard_count_str = data.get('shard-count')
    try:
        new_shard_count = int(new_shard_count_str)
    except ValueError:
        print("SHARD_COUNT is not a valid integer.")
    
    max_shard_groups = math.floor(len(view_list) / 2) # if you divide by 2, that's how many groups of two you can have (take the floor for odd numbers aka 1 group of 3)

    if new_shard_count > max_shard_groups:
        return make_response(jsonify({"error": "Not enough nodes to provide fault tolerance with requested shard count"}),400)

    # Proceed with resharding ....
    print(f"New shard count: {new_shard_count}")
    start_reshard(new_shard_count)

    # Make response
    return make_response(jsonify({"result": "resharded"}), 200)

def start_reshard(new_shard_count):
    # Get globals 
    global view_list, shard_groups, shard_count, hash_ring, shard_number, key_value_store

    # Make a local kvs copy that holds the entire store
    entire_kvs_copy = {}

    # Try to contact at least 1 person from each shard
    for i in range(shard_count):
        print(f"Trying to contact someone in shard group: {i}")
        for replica in shard_groups[i][:]:
            if replica != my_socket_address:
                try:
                    # Get the kvs & vc from each shard
                    url = f"http://{replica}/get-kvs-vc"
                    response = requests.get(url)
                    if response.status_code != 200:
                        # Unexpected behavior
                        continue
                    else:
                        # Get data
                        data = response.json()

                        # Check that kvs and vc is in data
                        if 'kvs' not in data and 'vc' not in data:
                            continue                #Unexpected behavior

                        entire_kvs_copy.update(data.get('kvs'))
                        merge_vector_clocks(data.get('vc'))
                        break
                except requests.exceptions.RequestException as e:
                    print(f'Unable to get {replica} information in reshard: {e}')      #TODO: delete broadcast!!!!

    # Update shard_count
    shard_count = new_shard_count

    # Now parition the kvs into the new shard count
    partitioned_kvs = []

    # Initialize the partitioned kvs 
    for i in range(new_shard_count):
        partitioned_kvs.append({})  # Initialize an empty dictionary for each shard
        print(f"Partitioned_kvs: {partitioned_kvs}")

    # Now iterate over the entire kvs and split data into the partitioned kvs
    for key, value in entire_kvs_copy.items():
        # Find out where this key:value will go 
        key_shard_destination = get_key_shard_desination(key)
        # key_shard_destination = get_shard_group(hash_ring.hash_key_to_node(key))
        
        # Insert into correct partition
        partitioned_kvs[key_shard_destination][key] = value

    
    # Now partition the new shard groups
    shard_groups.clear()
    shard_groups = make_shard_groups()
    print(f"View for new shard groups: {view_list}")
    print(f"New shard groups in reshard: {shard_groups}")

    # Now send new info to each shard
    for replica in view_list[:]:
        if replica == my_socket_address:
            # Update shard-number
            # shard_number = view_list.index(my_socket_address) % shard_count 
            shard_number = get_shard_number(my_socket_address)

            # Update kvs
            key_value_store = partitioned_kvs[shard_number]
        else:
            try:
                # Find out what shard-group this replica is in 
                # replica_shard_number = view_list.index(replica) % shard_count 
                replica_shard_number = get_shard_number(replica)
                url = f"http://{replica}/reshard-sheep"
                data = {'kvs': partitioned_kvs[replica_shard_number], 'vc': vector_clock, 'shard-groups': shard_groups, 'shard-count': shard_count}
                response = requests.put(url, json=data, timeout=10)
                if response.status_code != 200:
                    print(f"Unexpected behavior from {replica}, {response.status_code}")
                    pass #TODO: unexpected behavior
            except requests.exceptions.RequestException as e:
                print(f'cannot send new data for reshard to {replica}: {e}')
                #TODO: delete broadcast

@app.route('/reshard-sheep', methods=['PUT'])
def sheep_reshard():
    # Get globals
    global vector_clock, key_value_store, shard_groups, shard_count, shard_number, hash_ring

    # Get data
    data =  request.get_json()

    # Check that vc, kvs, shard-groups, shard-count is in data
    if 'kvs' not in data or 'vc' not in data or 'shard-groups' not in data or 'shard-count' not in data:
       return make_response(jsonify({'error': 'Not all data is provided'}), 400)

    # Get new vc, kvs, shard-groups, shard-count & update
    vector_clock.clear()
    vector_clock = data.get('vc')

    key_value_store.clear()
    key_value_store = data.get('kvs')

    shard_groups.clear()
    shard_groups_str = data.get('shard-groups')
    shard_groups = {int(k): v for k, v in shard_groups_str.items()} # convert string to ints
    print(f"Shard-sheep, shard-groups: {shard_groups}")

    shard_count_str = data.get('shard-count')             
    shard_count = int(shard_count_str)

    # Update shard-number & hash-ring
    # shard_number = view_list.index(my_socket_address) % shard_count 
    shard_number = get_shard_number(my_socket_address)

    print(f"Shard sheep update: {shard_groups}")
    # Return response
    return make_response(jsonify({'result': 'Updated'}), 200)

@app.route('/get-kvs-vc', methods=['GET'])
def get_kvs_vc():
    # Get globals
    global key_value_store, vector_clock

    return make_response(jsonify({'kvs': key_value_store, 'vc': vector_clock}), 200)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                                       INITIALIZE GLOABLS
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# Get environment variable for socket address 
my_socket_address = os.getenv('SOCKET_ADDRESS')

# Get environment variable for view list
my_view = os.getenv('VIEW')

# Get environment variable for shard count
shard_count_str = os.getenv('SHARD_COUNT')

if shard_count_str is not None:
    try:
        shard_count = int(shard_count_str)
    except ValueError:
        print("SHARD_COUNT is not a valid integer.")
else:
    print("SHARD_COUNT environment variable is not set.")
    shard_count = None

# Create a view list to keep track of running replicas
view_list = my_view.split(",") if my_view else []
view_list.sort()

# Create vector clock that has everyone in your view list
vector_clock = {key: 0 for key in view_list}

# Create a key value store dictionary
key_value_store = {} 

# Create a shard group, this is the group that this repllica will be in
if shard_count is not None:
    shard_groups = make_shard_groups()
else:
    shard_groups = None


# Create a shard number, this is the group number that this replica will be in
if shard_count is not None:
    shard_number = view_list.index(my_socket_address) % shard_count 
    print(f"{my_socket_address} is in shard group {shard_number}")
else:
    shard_number = None
    print(f"No shard_count, I'm not apart of any shard group yet ...")



# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                              INITIALIZE ON STARTUP (ONLY BROADCAST YOUR VIEW) 
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


broadcast_view('PUT', my_socket_address)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090, debug=True)