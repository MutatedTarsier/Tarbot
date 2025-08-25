class MyQueue:
    def __init__(self):
        self.__queue = []
        self.__size = 0
        
    def enqueue(self, item):
        self.__queue.append(item)
        self.__size += 1
        
    def dequeue(self):
        if self.__size == 0:
            return None
        else:
            self.__size -= 1
            return self.__queue.pop(0)
    def peek(self):
        return self.__queue[0]
    def empty(self):
        return self.__size == 0
    def getSize(self):
        return self.__size
    def get(self):
        output = []
        for element in self.__queue:
            output.append(element)
        return output
    def remove(self, position):
        self.__size -= 1
        return self.__queue.pop(position - 1)
    def add(self, element, position):
        self.__size += 1
        self.__queue.insert(position, element)