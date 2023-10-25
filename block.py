import pickle, logging

import blockserver
import fsconfig
import xmlrpc.client, socket, time

#### BLOCK LAYER

# global TOTAL_NUM_BLOCKS, BLOCK_SIZE, INODE_SIZE, MAX_NUM_INODES, MAX_FILENAME, INODE_NUMBER_DIRENTRY_SIZE

class DiskBlocks():
    def __init__(self):

        # initialize clientID
        if fsconfig.CID >= 0 and fsconfig.CID < fsconfig.MAX_CLIENTS:
            self.clientID = fsconfig.CID
        else:
            print('Must specify valid cid')
            quit()

        # initialize XMLRPC client connection to raw block server
        if fsconfig.PORT:
            PORT = fsconfig.PORT
        else:
            print('Must specify port number')
            quit()
        server_url = 'http://' + fsconfig.SERVER_ADDRESS + ':' + str(PORT)
        self.block_server = xmlrpc.client.ServerProxy(server_url, use_builtin_types=True)
        socket.setdefaulttimeout(fsconfig.SOCKET_TIMEOUT)

        self.cacheDist = {}



    ## Put: interface to write a raw block of data to the block indexed by block number
    ## Blocks are padded with zeroes up to BLOCK_SIZE

    def Put(self, block_number, block_data):

        if block_number == fsconfig.TOTAL_NUM_BLOCKS - 2 or block_number == fsconfig.TOTAL_NUM_BLOCKS - 1:
            logging.error('CACHE_INVALIDATED: ' + str(block_number))
            print("CACHE_INVALIDATED")

        logging.debug(
            'Put: block number ' + str(block_number) + ' len ' + str(len(block_data)) + '\n' + str(block_data.hex()))
        if len(block_data) > fsconfig.BLOCK_SIZE:
            logging.error('Put: Block larger than BLOCK_SIZE: ' + str(len(block_data)))
            quit()

        last_cid = bytearray(self.block_server.Get(fsconfig.TOTAL_NUM_BLOCKS-2))[0]
        if last_cid != self.clientID:
            logging.error("CACHE_INVALIDATED")
            print("CACHE_INVALIDATED")
            quit()

        if block_number in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            # ljust does the padding with zeros
            putdata = bytearray(block_data.ljust(fsconfig.BLOCK_SIZE, b'\x00'))
            # Write block
            # commenting this out as the request now goes to the server
            # self.block[block_number] = putdata
            # call Put() method on the server; code currently quits on any server failure
            execute = False
            while (not execute):
                try:
                    ret = self.block_server.Put(block_number, putdata)
                    bytecid = bytearray(self.clientID)
                    cid = bytearray(bytecid.ljust(fsconfig.BLOCK_SIZE, b'\x00'))
                    self.block_server.Put(fsconfig.BLOCK_SIZE-2, cid)
                    # write-through
                    self.cacheDist[block_number] = bytearray(putdata)
                    print("CACHE_WRITE_THROUGH " + str(block_number))
                    execute = True
                except socket.timeout:
                    logging.error('SERVER_TIMED_OUT')
                    print("SERVER_TIMED_OUT_PUT")
                    #time += fsconfig.SOCKET_TIMEOUT
            # ret = self.block_server.Put(block_number, putdata)
            if ret == -1:
                logging.error('Put: Server returns error')
                quit()
            return 0
        else:
            logging.error('Put: Block out of range: ' + str(block_number))
            quit()


    ## Get: interface to read a raw block of data from block indexed by block number
    ## Equivalent to the textbook's BLOCK_NUMBER_TO_BLOCK(b)

    def Get(self, block_number):

        logging.debug('Get: ' + str(block_number))

        if block_number == fsconfig.TOTAL_NUM_BLOCKS - 2 or block_number == fsconfig.TOTAL_NUM_BLOCKS - 1:
            logging.error('CACHE_INVALIDATED: ' + str(block_number))
            print("CACHE_INVALIDATED")

        if block_number in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            # logging.debug ('\n' + str((self.block[block_number]).hex()))
            # commenting this out as the request now goes to the server
            # return self.block[block_number]
            # call Get() method on the server
            # if the block in cache --> hit the cache, get from cache
            bytecid = bytearray(self.clientID)
            cid = bytearray(bytecid.ljust(fsconfig.BLOCK_SIZE, b'\x00'))
            self.block_server.Put(fsconfig.BLOCK_SIZE - 2, cid)

            if block_number in self.cacheDist:
                print("CACHE_HIT "+ str(block_number))
                return self.cacheDist[block_number]
            # not hit the cache --> store to the cache
            print("CACHE_MISS " + str(block_number))
            execute = False
            while (not execute):
                try:
                    data = self.block_server.Get(block_number)
                    self.cacheDist[block_number] = bytearray(data)
                    execute = True
                except socket.timeout:
                    print("SERVER_TIMED_OUT_GET")
            # return as bytearray
            return bytearray(data)

        logging.error('DiskBlocks::Get: Block number larger than TOTAL_NUM_BLOCKS: ' + str(block_number))
        quit()

    def RSM(self, block_number):
        logging.debug('RSM: ' + str(block_number))
        if block_number in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            execute = False
            while (not execute):
                try:
                    data = self.block_server.RSM(block_number)
                    execute = True
                except socket.timeout:
                    print("SERVER_TIMED_OUT_RSM")
            return bytearray(data)
        logging.error('DiskBlocks::RSM: Block number larger than TOTAL_NUM_BLOCKS: ' + str(block_number))
        quit()


    def Acquire(self):
        logging.debug('Acquire')
        # the first byte of the block to signify the lock
        lock = self.block_server.RSM(fsconfig.TOTAL_NUM_BLOCKS-1)[0]
        # 0 == released
        # 1 == acquired
        # spin-block
        # if there is a lock, then fall in to spin-block
        while lock == 1:
            # wait for 1 second
            time.sleep(1)
            lock = self.block_server.RSM(fsconfig.TOTAL_NUM_BLOCKS - 1)[0]
        return 0


    def Release(self):
        logging.debug('Release')
        RSM_UNLOCKED = bytearray(b'\x00') * 1
        self.Put(fsconfig.TOTAL_NUM_BLOCKS-1, bytearray(RSM_UNLOCKED.ljust(fsconfig.BLOCK_SIZE, b'\x00')))
        return 0






    ## Serializes and saves the DiskBlocks block[] data structure to a "dump" file on your disk

    def DumpToDisk(self, filename):

        logging.info("DiskBlocks::DumpToDisk: Dumping pickled blocks to file " + filename)
        file = open(filename,'wb')
        file_system_constants = "BS_" + str(fsconfig.BLOCK_SIZE) + "_NB_" + str(fsconfig.TOTAL_NUM_BLOCKS) + "_IS_" + str(fsconfig.INODE_SIZE) \
                            + "_MI_" + str(fsconfig.MAX_NUM_INODES) + "_MF_" + str(fsconfig.MAX_FILENAME) + "_IDS_" + str(fsconfig.INODE_NUMBER_DIRENTRY_SIZE)
        pickle.dump(file_system_constants, file)
        pickle.dump(self.block, file)

        file.close()

    ## Loads DiskBlocks block[] data structure from a "dump" file on your disk

    def LoadFromDump(self, filename):

        logging.info("DiskBlocks::LoadFromDump: Reading blocks from pickled file " + filename)
        file = open(filename,'rb')
        file_system_constants = "BS_" + str(fsconfig.BLOCK_SIZE) + "_NB_" + str(fsconfig.TOTAL_NUM_BLOCKS) + "_IS_" + str(fsconfig.INODE_SIZE) \
                            + "_MI_" + str(fsconfig.MAX_NUM_INODES) + "_MF_" + str(fsconfig.MAX_FILENAME) + "_IDS_" + str(fsconfig.INODE_NUMBER_DIRENTRY_SIZE)

        try:
            read_file_system_constants = pickle.load(file)
            if file_system_constants != read_file_system_constants:
                print('DiskBlocks::LoadFromDump Error: File System constants of File :' + read_file_system_constants + ' do not match with current file system constants :' + file_system_constants)
                return -1
            block = pickle.load(file)
            for i in range(0, fsconfig.TOTAL_NUM_BLOCKS):
                self.Put(i,block[i])
            return 0
        except TypeError:
            print("DiskBlocks::LoadFromDump: Error: File not in proper format, encountered type error ")
            return -1
        except EOFError:
            print("DiskBlocks::LoadFromDump: Error: File not in proper format, encountered EOFError error ")
            return -1
        finally:
            file.close()


## Prints to screen block contents, from min to max

    def PrintBlocks(self,tag,min,max):
        print ('#### Raw disk blocks: ' + tag)
        for i in range(min,max):
            print ('Block [' + str(i) + '] : ' + str((self.Get(i)).hex()))
