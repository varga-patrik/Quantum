//forrás: https://learn.microsoft.com/en-us/windows/win32/winsock/complete-client-code
//ez a link tartalmazza a kliens skeletont, amit felhasznaltam

#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdlib.h>
#include <stdio.h>
#include <vector>
#include <iostream>
#include <filesystem>
#include <sstream>
#include "fs_util.h"
#include "KinesisUtil.h"
#include "Correlator.h"
#include "direct.h"
#include "orchestrator.h"

#pragma comment (lib, "Ws2_32.lib")
#pragma comment (lib, "Mswsock.lib")
#pragma comment (lib, "AdvApi32.lib")


#define DEFAULT_BUFLEN 512
#define DEFAULT_PORT "27015"

int recvAll(SOCKET socket, char* buffer, int length) {
    int totalReceived = 0;
    while (totalReceived < length) {
        int bytesReceived = recv(socket, buffer + totalReceived, length - totalReceived, 0);
        if (bytesReceived <= 0) return bytesReceived; // error or closed
        totalReceived += bytesReceived;
    }
    return totalReceived;
}

void WaitForCommandDone(SOCKET socket) {

    std::string message;

    while (message != "done")
    {
       //read 3 byte header
        char header[3];
        if (recvAll(socket, header, 3) <= 0) return;
        int readCount = ((unsigned char)header[0] << 16) |
                        ((unsigned char)header[1] << 8) |
                        (unsigned char)header[2];
        //read body
        std::vector<char> buffer(readCount);
        if (recvAll(socket, buffer.data(), readCount) <= 0) return; 
        message = std::string(buffer.begin(), buffer.end());
    }
}

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

void readReceivingFile(SOCKET socket, const std::vector<char>& firstChunk, int firstChunkSize) {
    std::ofstream outFile("temp_receiving.bin", std::ios::binary | std::ios::trunc);
    if (!outFile) {
        std::cerr << "Failed to create output file.\n";
        return;
    }
    
    // Write the first chunk we already received
    outFile.write(firstChunk.data(), firstChunkSize);
    
    char header[3];
    while (true) {
        if (recvAll(socket, header, 3) <= 0) break;
        
        int readCount = ((unsigned char)header[0] << 16) |
                       ((unsigned char)header[1] << 8) |
                       (unsigned char)header[2];
        
        std::vector<char> buffer(readCount);
        if (recvAll(socket, buffer.data(), readCount) <= 0) break;
        
        // Check for EOF marker
        const std::string eofPrefix = "EOF ";
        if (readCount >= eofPrefix.size() &&
            std::equal(eofPrefix.begin(), eofPrefix.end(), buffer.begin())) {
            
            std::string fileName(buffer.begin() + eofPrefix.size(), buffer.end());
            std::filesystem::path destPath = std::filesystem::path("C:\\Users\\MCL\\Documents\\VargaPatrik\\Quantum\\data") / fileName;
            outFile.close();
            std::filesystem::rename("temp_receiving.bin", destPath);
            std::cout << "Received file saved as " << destPath.string() << "\n";
            return; // Exit this function, outer loop will continue for next file
        }
        
        // Regular file data
        outFile.write(buffer.data(), readCount);
    }
    
    outFile.close();
}

int main(int argc, char **argv) 
{
    WSADATA wsaData;
    SOCKET ConnectSocket = INVALID_SOCKET;
    struct addrinfo *result = NULL,
                    *ptr = NULL,
                    hints;
    std::string sendbuf;
    char recvbuf[DEFAULT_BUFLEN];
    int iResult;
    int recvbuflen = DEFAULT_BUFLEN;

    //kapcsolat felepitese a gps oraval, output stringhez nem tartozik erdemi funkcio, azt korabban tesztelesre hasznaltam
    std::string ip_text = "172.26.34.159";
    std::string output = "diff_data.csv";
    FSUtil fs(6000, ip_text, output);

    char pathbuffer[1024];
    getcwd(pathbuffer, 1024);
    
    // Validate the parameters
    if (argc != 2) {
        printf("usage: %s server-name\n", argv[0]);
        return 1;
    }

    // Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
    if (iResult != 0) {
        printf("WSAStartup failed with error: %d\n", iResult);
        return 1;
    }

    ZeroMemory( &hints, sizeof(hints) );
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    // Resolve the server address and port
    iResult = getaddrinfo(argv[1], DEFAULT_PORT, &hints, &result);
    if ( iResult != 0 ) {
        printf("getaddrinfo failed with error: %d\n", iResult);
        WSACleanup();
        return 1;
    }

    // Attempt to connect to an address until one succeeds
    for(ptr=result; ptr != NULL ;ptr=ptr->ai_next) {

        // Create a SOCKET for connecting to server
        ConnectSocket = socket(ptr->ai_family, ptr->ai_socktype, 
            ptr->ai_protocol);
        if (ConnectSocket == INVALID_SOCKET) {
            printf("socket failed with error: %ld\n", WSAGetLastError());
            WSACleanup();
            return 1;
        }

        // Connect to server.
        iResult = connect( ConnectSocket, ptr->ai_addr, (int)ptr->ai_addrlen);
        if (iResult == SOCKET_ERROR) {
            closesocket(ConnectSocket);
            ConnectSocket = INVALID_SOCKET;
            continue;
        }
        break;
    }

    freeaddrinfo(result);

    if (ConnectSocket == INVALID_SOCKET) {
        printf("Unable to connect to server!\n");
        WSACleanup();
        return 1;
    }

    std::cout << "Connected to server" << std::endl;
    
    //ebben a while blokkban tortenik minden relevans funkcio
    //--------------------------------------------------------
    //fontos, hogy amikor teszteles keppen egy geprol, de ket kulonbozo terminalon futtatod a server es a client programot,
    //akkor valamelyik oldalon ki kell kommentelni a parancsok lefuttatasat, mivel mindket eszkoz ugyanazokkal a muszerekkel kommunikalna
    //nem tudom pontosan mekkora lenne a kar, valoszinuleg csak egy error az egyik oldalon, de ezek a muszerek eleg dragak, nem kockaztatnam
    //--------------------------------------------------------

    if(TLI_BuildDeviceList() == 0){
        KinesisUtil device_bme_4("55528174");
        KinesisUtil device_bme_2("55526814");

        device_bme_2.load();
        device_bme_4.load();

        device_bme_2.startPolling(200);
        device_bme_4.startPolling(200);

        //device_bme_2.home();
        //device_bme_4.home();
        Correlator correlator(100000, (1ULL << 16));
        Orchestrator orchstrator(fs, device_bme_2, 0.0, device_bme_4, 0.0, correlator, 
                                "C:\\Users\\MCL\\Documents\\VargaPatrik\\Quantum\\data", 5.0);

        while(!fs.is_same_str(sendbuf.c_str(), "exit")){

            std::ostringstream path;
            sendbuf = orchstrator.runNextStep();

            //setup parancs elokesziti a muszereket a meresre
            if(fs.is_same_str(sendbuf.c_str(), "setup")){
                fs.measure_setup();
                path.clear();
                path << "\"" << pathbuffer << "\\timetagger_setup.py\"";
                fs.run(path.str());
            }

            iResult = send( ConnectSocket, sendbuf.c_str(), DEFAULT_BUFLEN, 0 );

            if (iResult == SOCKET_ERROR) {
                printf("send failed with error: %d\n", WSAGetLastError());
                closesocket(ConnectSocket);
                WSACleanup();
                return 1;
            }

            else if(sendbuf.find("read_data_file") != std::string::npos){
                while (true) {
                    char header[3];
                    int headerResult = recvAll(ConnectSocket, header, 3);
                    if (headerResult <= 0) break;
                    
                    int messageSize = ((unsigned char)header[0] << 16) |
                                    ((unsigned char)header[1] << 8) |
                                    (unsigned char)header[2];
                    
                    std::vector<char> buffer(messageSize);
                    int bodyResult = recvAll(ConnectSocket, buffer.data(), messageSize);
                    if (bodyResult <= 0) break;
                    
                    // Check for EOT
                    std::string message(buffer.begin(), buffer.end());
                    if (message == "EOT") {
                        std::cout << "Finished receiving files." << std::endl;
                        break;
                    }
                    
                    // This must be the first chunk of a file - pass it to the receiver
                    readReceivingFile(ConnectSocket, buffer, messageSize);
                }
            }

            //ez a meres, a program megvarja a kezdes idopontjat es lefuttatja a merest
            else if (sendbuf.find("rotate") != std::string::npos) {
                std::istringstream iss(sendbuf);
                std::string command, deviceName, mode, startTimeStr;
                double durationSec = -1.0; // sentinel for "no measurement"

                // Parse the command
                iss >> command >> deviceName >> mode >> durationSec >> startTimeStr;

                // Rotate the device
                if (deviceName == "wigner2") {
                    // Only start acquisition if duration > 0 and startTimeStr is not empty
                    if (durationSec > 0 && !startTimeStr.empty()) {
                        // Wait until the specified GPS start time
                        fs.wait_until(startTimeStr.c_str());

                        // Build Python command
                        std::ostringstream path;
                        path << "\"" << pathbuffer << "\\timestamps_acquisition.py\""
                            << " --duration " << std::fixed << std::setprecision(2) << durationSec;

                        // Run acquisition
                        fs.run(path.str());
                        std::this_thread::sleep_for(std::chrono::seconds(static_cast<int>(durationSec) + 1)); // ensure file is written
                    }
                } 
            }

            //wait for "done"
            WaitForCommandDone(ConnectSocket);

        }

        device_bme_2.stopPolling();
        device_bme_4.stopPolling();
    }

    // shutdown the connection since no more data will be sent
    iResult = shutdown(ConnectSocket, SD_SEND);
    if (iResult == SOCKET_ERROR) {
        printf("shutdown failed with error: %d\n", WSAGetLastError());
        closesocket(ConnectSocket);
        WSACleanup();
        return 1;
    }

    // Receive until the peer closes the connection
    do {
        iResult = recv(ConnectSocket, recvbuf, recvbuflen, 0);
        if ( iResult > 0 )
            printf("Bytes received: %d\n", iResult);
        else if ( iResult == 0 )
            printf("Connection closed\n");
        else
            printf("recv failed with error: %d\n", WSAGetLastError());

    } while( iResult > 0 );

    // cleanup
    closesocket(ConnectSocket);
    WSACleanup();

    return 0;
}