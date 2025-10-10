//forrás: https://learn.microsoft.com/en-us/windows/win32/winsock/complete-server-code
//ez a link tartalmazza a szerver skeletont, amit felhasznaltam

#undef UNICODE

#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdlib.h>
#include <stdio.h>
#include <iostream>
#include <filesystem>
#include <sstream>
#include <vector>
#include "fs_util.h"
#include "KinesisUtil.h"
#include "direct.h"

// Need to link with Ws2_32.lib
#pragma comment (lib, "Ws2_32.lib")
// #pragma comment (lib, "Mswsock.lib")

#define DEFAULT_BUFLEN 512
#define DEFAULT_PORT "27015"

std::vector<std::string> uploadFiles(const std::string& folder, const std::string& condition) {
    std::vector<std::string> files;

    try {
        for (const auto& entry : std::filesystem::directory_iterator(folder)) {
            if (!entry.is_regular_file()) continue; 
            std::string filename = entry.path().filename().string();

            if (filename.find(condition) != std::string::npos) {
                files.push_back(entry.path().string());
            }
        }
    }
    catch (const std::filesystem::filesystem_error& e) {
        std::cerr << "Filesystem error: " << e.what() << std::endl;
    }

    return files;
}

void sendFile(SOCKET clientSocket, const std::string& filePath) {
    // Open the file
    std::ifstream file(filePath, std::ios::binary);
    if (!file) {
        std::cerr << "Failed to open file: " << filePath << std::endl;
        return;
    }

    size_t chunkSize = DEFAULT_BUFLEN;
    uint64_t* dataPoints = new uint64_t[chunkSize];
    while (file.read(reinterpret_cast<char*>(dataPoints), chunkSize * sizeof(uint64_t)) || file.gcount()) {
        size_t readCount = file.gcount() / sizeof(uint64_t);
        char* buffer = new char[readCount];
        for(size_t i = 0; i < readCount; ++i) {
            buffer[i] = static_cast<char>(dataPoints[i] & 0xFF); 
        }
        //send read count bytes, make sure the client gets 3 bytes at a time
        char readCountBuffer[3];
        readCountBuffer[0] = static_cast<char>((readCount >> 16) & 0xFF);
        readCountBuffer[1] = static_cast<char>((readCount >> 8) &   0xFF);
        readCountBuffer[2] = static_cast<char>(readCount & 0xFF);
        int errorCode = send(clientSocket, readCountBuffer, 3, 0);
        if (errorCode == SOCKET_ERROR) {
            std::cerr << "Failed to send read count for file: " << filePath << std::endl;
            break;
        }

        errorCode = send(clientSocket, buffer, readCount, 0);
        if (errorCode == SOCKET_ERROR) {
            std::cerr << "Failed to send file: " << filePath << std::endl;
            break;
        }
        delete[] buffer;
    }
    delete[] dataPoints;

    //Send end-of-file marker and file name
    std::string eofMarker = "EOF " + std::filesystem::path(filePath).filename().string();

    //send the length of the eof marker in 3 bytes followed by the eof marker itself
    size_t eofMarkerSize = eofMarker.size();
    int errorCode = send(clientSocket, reinterpret_cast<const char*>(&eofMarkerSize), 3, 0);

    errorCode = send(clientSocket, eofMarker.c_str(), eofMarker.size(), 0);
    if (errorCode == SOCKET_ERROR) {
        std::cerr << "Failed to send EOF marker for file: " << filePath << std::endl;
    }

    file.close();
}

int main(void) 
{
    WSADATA wsaData;
    int iResult;

    SOCKET ListenSocket = INVALID_SOCKET;
    SOCKET ClientSocket = INVALID_SOCKET;

    struct addrinfo *result = NULL;
    struct addrinfo hints;

    int iSendResult;
    char recvbuf[DEFAULT_BUFLEN];
    int recvbuflen = DEFAULT_BUFLEN;

    //kapcsolat felepitese a gps oraval, output stringhez nem tartozik erdemi funkcio, azt korabban tesztelesre hasznaltam
    std::string ip_text = "148.6.27.165";
    std::string output = "diff_data.csv";
    FSUtil fs(5, ip_text, output);

    char pathbuffer[1024];
    getcwd(pathbuffer, 1024);
    
    // Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
    if (iResult != 0) {
        printf("WSAStartup failed with error: %d\n", iResult);
        return 1;
    }

    ZeroMemory(&hints, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    hints.ai_flags = AI_PASSIVE;

    // Resolve the server address and port
    iResult = getaddrinfo(NULL, DEFAULT_PORT, &hints, &result);
    if ( iResult != 0 ) {
        printf("getaddrinfo failed with error: %d\n", iResult);
        WSACleanup();
        return 1;
    }

    // Create a SOCKET for the server to listen for client connections.
    ListenSocket = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (ListenSocket == INVALID_SOCKET) {
        printf("socket failed with error: %ld\n", WSAGetLastError());
        freeaddrinfo(result);
        WSACleanup();
        return 1;
    }

    // Setup the TCP listening socket
    iResult = bind( ListenSocket, result->ai_addr, (int)result->ai_addrlen);
    if (iResult == SOCKET_ERROR) {
        printf("bind failed with error: %d\n", WSAGetLastError());
        freeaddrinfo(result);
        closesocket(ListenSocket);
        WSACleanup();
        return 1;
    }

    freeaddrinfo(result);

    std::cout << "Listening for connection" << std::endl;
    iResult = listen(ListenSocket, SOMAXCONN);
    if (iResult == SOCKET_ERROR) {
        printf("listen failed with error: %d\n", WSAGetLastError());
        closesocket(ListenSocket);
        WSACleanup();
        return 1;
    }

    // Accept a client socket
    ClientSocket = accept(ListenSocket, NULL, NULL);
    if (ClientSocket == INVALID_SOCKET) {
        printf("accept failed with error: %d\n", WSAGetLastError());
        closesocket(ListenSocket);
        WSACleanup();
        return 1;
    }

    std::cout << "Client accepted" << std::endl;

    // No longer need server socket
    closesocket(ListenSocket);

    //ebben a while blokkban tortenik minden relevans funkcio, itt fogadja a szerver a kliens uzeneteit
    //--------------------------------------------------------
    //fontos, hogy amikor teszteles keppen egy geprol, de ket kulonbozo terminalon futtatod a server es a client programot,
    //akkor valamelyik oldalon ki kell kommentelni a parancsok lefuttatasat, mivel mindket eszkoz ugyanazokkal a muszerekkel kommunikalna
    //nem tudom pontosan mekkora lenne a kar, valoszinuleg csak egy error az egyik oldalon, de ezek a muszerek eleg dragak, nem kockaztatnam
    //--------------------------------------------------------

    KinesisUtil device_wigner_4("12345897");
    KinesisUtil device_wigner_2("12345897");

    device_wigner_2.home();
    device_wigner_4.home();

    double rotation_stages[19] = { 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90 };
    int counter_wigner_4 = 0;
    int counter_wigner_2 = 0;

    std::vector<uint64_t> results;

    do {
        std::ostringstream path;
        iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
        if (iResult > 0) {

            //setup parancs elokesziti a muszereket a meresre
            /*if(fs.is_same_str(recvbuf, "setup")){
                fs.measure_setup();
                path.clear();
                path << "\"" << pathbuffer << "\\timetagger_setup.py\"";
                fs.run(path.str());
            }

            //ez a meres, a program megvarja a kezdes idopontjat es lefuttatja a merest
            else if(fs.is_in(recvbuf, "start")){
                fs.wait_until(recvbuf + 6);
                path.clear();
                path << "\"" << pathbuffer << "\\timestamps_acquisition.py\"";
                fs.run(path.str());
            }*/

            if(fs.is_same_str(recvbuf, "activate wigner")){
                device_wigner_2.activate();
                device_wigner_4.activate();
            }

            if(fs.is_same_str(recvbuf, "deactivate wigner")){
                device_wigner_2.deactivate();
                device_wigner_4.deactivate();
            }

            if(fs.is_same_str(recvbuf, "read_data_file")){
                std::vector<std::string> files = uploadFiles("./data", "bme");
                for (const auto& file : files) {
                    sendFile(ClientSocket, file);
                }

                //Send end-of-transmission marker
                int errorCode = send(ClientSocket, "EOT", 3, 0);
                if (errorCode == SOCKET_ERROR) {
                    std::cerr << "Failed to send EOT marker" << std::endl;
                }
            }

            if (fs.is_same_str(recvbuf, "rotate")) {
                if(device_wigner_2.isActive() && device_wigner_4.isActive()){
                    
                    if (counter_wigner_2 == 18) {

                        if (!device_wigner_4.moveToPosition(rotation_stages[counter_wigner_4])) {
                            std::cout << "ERROR with wigner 4" << std::endl;
                        }

                        if (!device_wigner_2.moveToPosition(rotation_stages[counter_wigner_2])) {
                            std::cout << "ERROR with wigner 2" << std::endl;
                        }
                        counter_wigner_2 = 0;
                        counter_wigner_4++;
                    }
                    else {

                        if (!device_wigner_4.moveToPosition(rotation_stages[counter_wigner_4])) {
                            std::cout << "ERROR with wigner 4" << std::endl;
                        }

                        if (!device_wigner_2.moveToPosition(rotation_stages[counter_wigner_2])) {
                            std::cout << "ERROR with wigner 2" << std::endl;
                        }

                        counter_wigner_2++;
                    }

                    std::cout<< "Current position: "<< std::endl << "Wigner4: " << rotation_stages[counter_wigner_4] 
                    << std::endl << "Wigner2: " << rotation_stages[counter_wigner_2] << std::endl; 
                }
            }

            std::cout << std::endl << "Recieved: " << recvbuf << std::endl;
        }
        else if (iResult == 0)
            printf("Connection closing...\n");
        else  {
            printf("recv failed with error: %d\n", WSAGetLastError());
            closesocket(ClientSocket);
            WSACleanup();
            return 1;
        }

    } while (iResult > 0);

    // shutdown the connection since we're done
    iResult = shutdown(ClientSocket, SD_SEND);
    if (iResult == SOCKET_ERROR) {
        printf("shutdown failed with error: %d\n", WSAGetLastError());
        closesocket(ClientSocket);
        WSACleanup();
        return 1;
    }

    // cleanup
    closesocket(ClientSocket);
    WSACleanup();

    return 0;
}