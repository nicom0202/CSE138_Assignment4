from flask import Flask, make_response, jsonify, request
import requests
import os
import time
app = Flask(__name__)


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#      GET ENVIRONMENT VARIABLES 
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================

# Get environment variable for socket address 
my_socket_address = os.getenv('SOCKET_ADDRESS')

# Get environment variable for view list
my_view = os.getenv('VIEW')

# Get environment variable for shard count
shard_count = os.getenv('SHARD_COUNT')


# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
# INITIALIZE GLOABLS:            VIEW_LIST,   VECTOR_CLOCK,   KEY_VALUE_STORE,    SHARD_NUMBER
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================

# Create a view list to keep track of running replicas
view_list = my_view.split(",") if my_view else []
view_list.sort()

# Create vector clock that has everyone in your view list
vector_clock = {key: 0 for key in view_list}

# Create a key value store dictionary
key_value_store = {} 

# Create a shard number, this is the group number that this replica will be in
shard_number = view_list.index(my_socket_address) % shard_count 


# TODO: WHY IS HISTORY NEEDED??????
'''
# History is a list of events.
# Note: history is not ordered so use the vector clock values for ordering
# Events are logged as follows:
#   ["PUT"/"GET", key, value_after_operation, clock_after_operation]

HISTORY = []
'''





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



# Create a shard group, this is the group that this repllica will be in
shard_groups = make_shard_groups()













# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
# HELPER FUNCTIONS:                   BROADCASTING UPDATES TO VIEW
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


# This function will broadcast my_socket_address to everyone in my view_list
def broadcast_my_view():
    # Get gloabls
    global view_list, my_socket_address

    # Broadcast to everyone to PUT your socket-address in other replicas view list
    for replica in view_list[:]:
        if replica != my_socket_address:
                try:
                    data = {'socket-address': my_socket_address}
                    url = f"http://{replica}/view"
                    requests.put(url, json=data, timeout=1)
                except requests.exceptions.RequestException as e:
                    # No need to delete/broadcast replica bc it will eventually get detected and broadcasted 
                    print(f"Exception caught in broadcast_my_view() to {replica}: {e}")

# This function will broadcast a /view DELETE to everyone (aka found a down replica, tell everyone to delete it)
def broadcast_delete_view(bad_replica_address):
    # Get globals
    global view_list
    
    # Broadcast to everyone in your view that you found a down replica
    for replica in view_list[:]:
        if replica != my_socket_address:
            try:
                data = {'socket-address': bad_replica_address}
                url = f"http://{replica}/view"
                requests.delete(url, json=data, timeout=5)
            except requests.exceptions.RequestException as e:
                # This will eventually get caught again when someone tries to broadcast another update
                print(f"Failed to connect to {replica} in delete broadcast ... error message: {e}")














# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /view endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


#           ~~~~~~~~~~~~~~~~~~~~~
#          ~~~~~ /view PUT ~~~~~~~
#           ~~~~~~~~~~~~~~~~~~~~~
@app.route('/view', methods=['PUT'])
def add_replica_to_view():  
    # Get globals
    global view_list

    # Get data from request
    data = request.get_json()

    # Check if data is None or empty
    if data is None:
        return make_response(jsonify({'error': 'Bad request, empty data'}), 400)

    new_socket_address = data.get('socket-address')

    # Check if socket-address exists in the data
    if new_socket_address is None:
        return make_response(jsonify({'error': 'Bad request, missing socket-address'}), 400)

    # Check if the socket already exists in their view
    if new_socket_address in view_list:
        return make_response(jsonify({"result": "already present"}), 200)


    # Add new replica to view list
    if new_socket_address not in view_list:
        view_list.append(new_socket_address)
        view_list.sort()

    # Add new replica address in vector clock
    if new_socket_address not in vector_clock:
        vector_clock[new_socket_address] = 0

    # Make response
    return make_response(jsonify(data={"result": "added"}), 201)


#           ~~~~~~~~~~~~~~~~~~~~~
#          ~~~~~ /view GET ~~~~~~~
#           ~~~~~~~~~~~~~~~~~~~~~
@app.route('/view', methods=['GET'])
def get_view():
    # Get globals
    global view_list
    # Make response
    return make_response(jsonify({"view": view_list}), 200)


#           ~~~~~~~~~~~~~~~~~~~~~
#          ~~~~~ /view DELETE ~~~~
#           ~~~~~~~~~~~~~~~~~~~~~
@app.route('/view', methods=['DELETE'])
def remove_a_replica_from_view():
    # Get globals
    global view_list

    # Get data from request
    data = request.get_json()

    # Check if data is None or empty
    if data is None:
        return make_response(jsonify({'error': 'Bad request, empty data'}), 400)

    delete_socket_address = data.get('socket-address')

    # Check if socket-address exists in the data
    if delete_socket_address is None:
        return make_response(jsonify({'error': 'Bad request, missing socket-address'}), 400)

    # Check if socket-address exists in your view
    if delete_socket_address in view_list and delete_socket_address != my_socket_address:
        view_list.remove(delete_socket_address)
        return make_response(jsonify({"result": "deleted"}), 200)
    
    return make_response(jsonify({"error": "View has no such replica"}), 404)







# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#      HELPER FUNCTIONS FOR VECTOR CLOCKS       
#                                               TODO: UPDATE VECTOR CLOCK LOGIC (ONLY COMPARE VC'S IN YOUR SHARD GROUP)
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


def update_vector_clock():
    # Get globals
    global vector_clock
    # Update your socket address in vector clock
    vector_clock[my_socket_address] += 1

def dependency_test_client(VC2): #NOTE: VC2 is the vector_clock of the requesting client
    # Get globals
    global vector_clock, view_list
    VC1 = vector_clock.copy()

    # check if VC2 is empty
    if VC2 is None:
        return True
    # Only compare addresses in view list (NOTE: We're not deleting vc info on replicas that are down)
    for address in view_list:
        if address in VC2:
            if VC1[address] < VC2[address]:
                return False
    
    return True

def dependency_test_replica(VC2, sender): #NOTE: VC2 is the vector_clock of the requesting replica and sender is the requesting replica socket-address
    # Get global
    global vector_clock, view_list
    VC1 = vector_clock.copy()

    # Check that the sender vc is only 1 ahead of your vc
    if VC2[sender] != VC1[sender] + 1:
        return False
    
    # Check that the sender vc knows the same amount of writes as you
    for key in view_list:
        if key in VC2:
            if key != sender and VC2[key] > VC1[key]:
                return False
    return True

# Helper funciton to merge vector clocks
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


# This function will broadcast to everyone in your shard group to PUT a key:value into the key-value-store
def broadcast_kvs_put(key, value):
    # Get globals
    global shard_groups, my_socket_address, shard_number

    # Create a list to hold replicas that are down
    down_replicas = []

    # Broadcast to everyone in shard group (skip yourself), to PUT a key in kvs
    for replica in shard_groups[shard_number][:]:
        if replica != my_socket_address:
            while True:
                try:
                    # Create request
                    url = f"http://{replica}/kvs/{key}"
                    data = {'value': value, 'causal-metadata': vector_clock}
                    headers = {'Replica': my_socket_address}
                    response = requests.put(url, json=data, headers=headers,timeout=5)
                    # Dependencies are NOT met, sleep and try again
                    if response.status_code == 503:
                        time.sleep(1)
                        continue
                    # Dependencies ARE met, break the while loop & continue the for-loop
                    elif response.status_code == 200 or response.status_code == 201:
                        break
                    
                    # Unexpected behavior
                    else:
                        raise Exception
                except requests.RequestException:
                    # Found down replica, delete from view list & add to down_replicas
                    if replica in view_list and replica != my_socket_address:
                        view_list.remove(replica)
                    down_replicas.append(replica)
                    break  # Continue to for loop iteration and break while loop iteration(aka next replica)

    # If you find any replicas that are down, broadcast it  
    if len(down_replicas) > 0 and len(view_list) != 1:
        for replica in down_replicas:
            broadcast_delete_view(replica)

# This function will broadcast to everyone in your shard group to DELETE a key:value into the key-value-store
def broadcast_kvs_delete(key):
    # Get globals
    global view_list, my_socket_address

    # Create a list to hold replicas that are down
    down_replicas = []

    # Broadcast to everyone in your shard group (skip yourself), to DELETE a key in kvs
    for replica in shard_groups[shard_number][:]:
        if replica != my_socket_address:
            while True:
                try:
                    # Create request
                    url = f"http://{replica}/kvs/{key}"
                    data = {'causal-metadata': vector_clock}
                    headers = {'Replica': my_socket_address}
                    response = requests.delete(url, json=data, headers=headers, timeout=5)
                    # Dependencies are NOT met, sleep and try again
                    if response.status_code == 503:
                        time.sleep(1)
                        continue
                    # Dependencies ARE met, break the while loop & continue the for-loop
                    elif response.status_code == 200 or response.status_code == 404:
                        break
                    # Unexpected behavior 
                    else:
                        raise Exception
                except requests.exceptions.RequestException:
                    # Found down replica, delete from view list & add to down_replicas
                    down_replicas.append(replica)
                    break  # Continue to for loop iteration and break while loop iteration(aka next replica)
                
    # if you find any replicas that are down, broadcast it  
    if len(down_replicas) > 0:
        for replica in down_replicas:
            if replica != my_socket_address:
                broadcast_delete_view(replica)















# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /kvs/<key> endpoint     NOTE: THIS ACTS AS A PROXY (RESPONSIBLE FOR FORWARDING TO CORRECT REPLICA)
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


@app.route('/kvs/<key>', methods=['PUT', 'GET', 'DELETE'])
def proxy_forward(key):
    # Get globals
    global shard_count, shard_number

    # Hash the key
    key_hash_value = hash(key)

    # Find out what shard this key is going to, hash_value % NUM_OF_SHARDS
    key_shard_destination = key_hash_value % shard_count

    # check if this key is in my shard group
    if key_shard_destination == shard_number:

        # Forward request to myself
        url = f"http://{my_socket_address}/replica/kvs/{key}"
        try:
            # forward respective method and return response to client
            if request.method == "PUT":
                response = requests.put(url, json=request.get_json(silent=True))
            elif request.method == "GET":
                response = requests.get(url, json=request.get_json(silent=True))
            elif request.method == "DELETE":
                response = requests.delete(url, json=request.get_json(silent=True))
            else:
                return make_response(jsonify({'error': 'Method Not Allowed'}), 405)
            
            # return response to client
            return response
        except requests.exceptions.RequestException as e:
            # forwarding request failed
            print(f'Could not forward to myself ... error: {e}')

    # forward to correct shard group
    else: 

        # Make a local variable to track down replcias
        down_replicas = []
        response = None

        # Forward to 1 replica in shard group  (NOTE: only forward to 1 because they will broadcast to everyone in their group)
        for replica in shard_groups[key_shard_destination][:]:

            # Forward request to shard with same shard number as the key
            url = f"http://{replica}/replica/kvs/{key}"
            try:
                # forward respective method and return response to client
                if request.method == "PUT":
                    response = requests.put(url, json=request.get_json(silent=True))
                elif request.method == "GET":
                    response = requests.get(url, json=request.get_json(silent=True))
                elif request.method == "DELETE":
                    response = requests.delete(url, json=request.get_json(silent=True))
                else:
                    return make_response(jsonify({'error': 'Method Not Allowed'}), 405)
                
                # break out of loop
                break

            except requests.exceptions.RequestException as e:
                # forwarding request failed
                print(f'Could not connect to {replica}: {e}')

                # Remove replica from view_list
                view_list.remove(replica)

                # Add replica is down_replicas
                down_replicas.append(replica)
                continue
        
        # Broadcast to everyone that a replica is down
        if len(down_replicas) > 0:
            for replica in down_replicas:
                if replica != my_socket_address:
                    broadcast_delete_view(replica)

        return response





















# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /replica/kvs/<key> endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================


#          ~~~~~~~~~~~~~~~~~~~~~
#          ~~~~~ PUT logic ~~~~~
#          ~~~~~~~~~~~~~~~~~~~~~
@app.route('/replica/kvs/<key>', methods=['PUT'])
def put_key_value(key):
    # Get global
    global key_value_store, vector_clock

    # Create a local variable
    status_code = 0

    # Get json data
    data = request.get_json(silent=True)

    # Check to see if data is empty
    if data is None:
        return make_response(jsonify({'error': 'data is none'}), 400)
    
    # Check that value exists in data
    if 'value' not in data:
        return make_response(jsonify({'error': 'PUT request does not specify a value'}), 400)
    
    value = data.get('value')

    # Check that casaul meta data exists in json
    if 'causal-metadata' not in data:
        return make_response(jsonify({'error': 'PUT request does not contain causal-metadata'}), 400) #TODO: might have to change this response to something else

    causal_metadata = data.get('causal-metadata')

    # Check header to see if request is from a client
    if 'Replica' not in request.headers:

        # Check dependencies
        if dependency_test_client(causal_metadata):
            
            # Check if key is to long
            if len(key) > 50:
                return make_response(jsonify({'error': 'Key is too long'}), 400)
            
            # Check if key exists or not in kvs
            if key in key_value_store:
                status_code = 200 # replaced
            else:
                status_code = 201 # created

            # Write to key value store
            key_value_store[key] = value

            # Merge vector clocks
            merge_vector_clocks(causal_metadata)

            # Update vector clock
            update_vector_clock()

            # Broadcast to everyone that a change has been made
            broadcast_kvs_put(key, value)

            # Reuslt was replaced
            if status_code == 200:
                return make_response(jsonify({"result": "replaced", "causal-metadata": vector_clock}), 200)
            # Result was created
            return make_response(jsonify({"result": "created", "causal-metadata": vector_clock}), 201)
        else:
            # Dependencies are NOT met
            return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)

    else: # From a replica
        
        # Dependency check for replica
        if dependency_test_replica(causal_metadata, request.headers.get('Replica')):

            # Check if key is to long
            if len(key) > 50:
                return make_response(jsonify({'error': 'Key is too long'}), 400)
            
            # Check if key exists in store
            if key in key_value_store:
                status_code = 200 # replaced
            else:
                status_code = 201 # created

            # Write to key value store
            key_value_store[key] = value

            # Merge vector clocks
            merge_vector_clocks(causal_metadata)

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
@app.route('/replica/kvs/<key>', methods=['GET'])
def get_key_value(key):

    # Get globals
    global key_value_store, vector_clock

    # Get json data
    data = request.get_json(silent=True)

    # Check to see if data is correct
    if data is None:
        return make_response(jsonify({'error': 'data is none'}), 400)
    
    # Now check that casaul meta data exists in json
    if 'causal-metadata' not in data:
        return make_response(jsonify({'error': 'PUT request does not contain causal-metadata'}), 400) #TODO: might have to change this response to something else

    causal_metadata = data.get('causal-metadata')

    # Check dependency test (only clients use this)
    if dependency_test_client(causal_metadata):

        # Merge the vector clocks
        merge_vector_clocks(causal_metadata)

        # Found key:value
        if key in key_value_store:
            return make_response(jsonify({"result": "found", "value": key_value_store[key], "causal-metadata": vector_clock}), 200)
        # Does not exist
        else: 
            return make_response(jsonify({"error": "Key does not exist"}), 404)
        
    else: 
        # Dependencies are NOT met
        return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)
    

#          ~~~~~~~~~~~~~~~~~~~~~~
#          ~~~~ DELETE logic ~~~~
#          ~~~~~~~~~~~~~~~~~~~~~~
@app.route('/replica/kvs/<key>', methods=['DELETE'])
def delete_key_value(key):

    # Get globals
    global key_value_store, vector_clock

    # Get json data
    data = request.get_json(silent=True)

    # Check to see if data is correct
    if data is None:
        return make_response(jsonify({'error': 'data is none'}), 400)
    
    # Check that casaul meta data exists in json
    if 'causal-metadata' not in data:
        return make_response(jsonify({'error': 'PUT request does not contain causal-metadata'}), 400) #TODO: might have to change this response to something else

    causal_metadata = data.get('causal-metadata')

    # Check header to see if request is from a client
    if 'Replica' not in request.headers:

        # Check dependencies
        if dependency_test_client(causal_metadata):
                        
            # Check if key exists in store
            if key not in key_value_store:
                return make_response(jsonify({"error": "Key does not exist"}), 404)

            # Delete key
            # with key_value_store_lock:
            del key_value_store[key]

            # Merge vector clocks
            merge_vector_clocks(causal_metadata)

            # Update vector clock 
            update_vector_clock()

            # Broadcast to everyone that a change has been made
            broadcast_kvs_delete(key)

            # Result was deleted
            return make_response(jsonify({"result": "deleted", "causal-metadata": vector_clock}), 200)
        else:
            # Dependencies are NOT met
            return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)

    else: # From a replica
        
        # Dependency check for replica
        if dependency_test_replica(causal_metadata, request.headers.get('Replica')):
            
            # Check if key is in the store
            if key not in key_value_store:
                return make_response(jsonify({"error": "Key does not exist"}), 404)

            # Delete key from store
            # with key_value_store_lock:
            del key_value_store[key]

            # Merge vector clocks
            merge_vector_clocks(causal_metadata)

            # Result was deleted
            return make_response(jsonify({"result": "deleted", "causal-metadata": vector_clock}), 200)
        else:
            # Dependencies are NOT met
            return make_response(jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503)











# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /shard/ids endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================
@app.route('/shard/ids', methods=['GET'])
def get_shard_ids():

    # Get globals
    global shard_groups

    # Make response
    return make_response(jsonify({'shard-ids': list(shard_groups.keys())}), 200)







# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /shard/node-shard-ids endpoint
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================
@app.route('/shard/node-shard-ids', methods=['GET'])
def get_node_shard_id():
    # Get globals
    global shard_number

    # Make respone
    return make_response(jsonify({'node-shard-id': shard_number}), 200)









# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /shard/members/<ID>
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================
@app.route('/shard/members/<ID>', methods=['GET'])
def get_shard_members(ID):

    # Get globals
    global shard_groups

    # Check if ID is in shard_groups
    if ID in shard_groups:
        return make_response(jsonify({'shard-members': shard_groups.get(ID)}), 200)
    
    # ID does not exist in shard_groups
    return make_response(jsonify({'error': 'No such shard ID exists'}), 404)








# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /shard/key-count/<ID>
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
        for replcia in view_list:
            if replica != my_socket_address:
                broadcast_delete_view(replcia)

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
#                  /shard/add-member/<ID>                   TODO: NEED A WAY FOR A REPLICA TO RETREIVE KVS AND VC WHEN ADDED TO A SHARD GROUP
#                                                           NOTE: SOLUTION: IF YOU'RE IN THAT SHARD GROUP & YOU RECIEVE THIS, SEND VC AND KVS TO NEW REPLICA
#                                                           NOTE: MAYBE ADD A NEW ENDPOINT CALLED /populate & SEND YOUR KVS/VC WHEN YOU GET A ADD-MEMBER IF ID IS YOUR SHARD_NUMBER
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
                broadcast_delete_view(replica)



@app.route('/shard/add-member/<ID>', methods=['PUT'])
def add_member(ID):

    # Get globals
    global view_list, shard_groups, key_value_store, vector_clock

    # Get the data from the request
    data = request.json()

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
        return make_response(jsonify({'error': f'{new_socket_address} does not exist in my view'}), 404)

    # Add new_socket_address to shard_groups[ID] IF it's not already there
    if new_socket_address not in shard_groups[ID]:
        shard_groups[ID].append(new_socket_address)

    # Check if this request is from a client
    if 'Replica' not in request.headers:
        # Broadcast to everyone to add this replica to shard_groups[ID]
        broadcast_add_member(ID, new_socket_address)

    # If ID is my shard group, send a PUT request to new_socket_address in /populate endpoint. Send KVS and VC
    if ID == shard_number:
        try:
            data = {'kvs': key_value_store, 'vc': vector_clock}
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
    global key_value_store, vector_clock

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

    # Make response 
    print(f"Updated kvs & vc from {data.get('Replica')}")
    return make_response(jsonify({'result': f"Updated kvs & vc from {data.get('Replica')}"}))







# ================================================================================================================
# ----------------------------------------------------------------------------------------------------------------
#                  /shard/reshard
# ----------------------------------------------------------------------------------------------------------------
# ================================================================================================================
def start_reshard():
    pass

@app.route('/shard/reshard', methods=['PUT'])
def reshard():
    pass





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090, debug=True)