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

void clampData(const std::string& folder, int64_t time_elapsed) {
    if (!std::filesystem::exists(folder)) return;

    const int64_t PICO_PER_SECOND = 1000000000000LL; // 10^12
    const size_t CHUNK_SIZE = 1024; // number of timestamps per chunk

    for (const auto& entry : std::filesystem::directory_iterator(folder)) {
        if (!std::filesystem::is_regular_file(entry)) continue;

        std::string filepath = entry.path().string();
        std::string tempFilepath = filepath + ".tmp";

        std::ifstream inFile(filepath, std::ios::binary);
        if (!inFile.is_open()) continue;

        std::ofstream outFile(tempFilepath, std::ios::binary | std::ios::trunc);
        if (!outFile.is_open()) {
            inFile.close();
            continue;
        }

        std::vector<std::pair<uint64_t, uint64_t>> buffer;
        buffer.reserve(CHUNK_SIZE);

        while (true) {
            buffer.clear();
            for (size_t i = 0; i < CHUNK_SIZE; ++i) {
                uint64_t picosec = 0, refSec = 0;
                inFile.read(reinterpret_cast<char*>(&picosec), sizeof(uint64_t));
                inFile.read(reinterpret_cast<char*>(&refSec), sizeof(uint64_t));
                if (inFile.gcount() < sizeof(uint64_t) * 2) break;

                int64_t totalPicosec = static_cast<int64_t>(picosec) + static_cast<int64_t>(refSec) * PICO_PER_SECOND;

                if (totalPicosec <= time_elapsed) {
                    buffer.emplace_back(picosec, refSec);
                }
            }

            // Write valid timestamps from this chunk
            for (const auto& ts : buffer) {
                outFile.write(reinterpret_cast<const char*>(&ts.first), sizeof(uint64_t));
                outFile.write(reinterpret_cast<const char*>(&ts.second), sizeof(uint64_t));
            }

            if (inFile.eof()) break;
        }

        inFile.close();
        outFile.close();

        std::filesystem::rename(tempFilepath, filepath); // replace original with clamped file
    }
}

void sendFile(SOCKET clientSocket, const std::string& filePath) {
    // Open the file
    std::ifstream file(filePath, std::ios::binary);
    if (!file) {
        std::cerr << "Failed to open file: " << filePath << std::endl;
        return;
    }

    const size_t chunkSize = DEFAULT_BUFLEN;
    std::vector<char> buffer(chunkSize);

    while (file) {
        file.read(buffer.data(), chunkSize);
        size_t readCount = file.gcount();
        if (readCount == 0) break;

        // send 3-byte header
        char header[3];
        header[0] = (readCount >> 16) & 0xFF;
        header[1] = (readCount >> 8) & 0xFF;
        header[2] = readCount & 0xFF;
        if (send(clientSocket, header, 3, 0) == SOCKET_ERROR) break;

        // send data
        if (send(clientSocket, buffer.data(), readCount, 0) == SOCKET_ERROR) break;
    }

    //Send end-of-file marker and file name
    std::string eofMarker = "EOF " + std::filesystem::path(filePath).filename().string();
    size_t markerLen = eofMarker.size();
    char header[3];
    header[0] = (markerLen >> 16) & 0xFF;
    header[1] = (markerLen >> 8) & 0xFF;
    header[2] = markerLen & 0xFF;
    send(clientSocket, header, 3, 0);
    send(clientSocket, eofMarker.c_str(), markerLen, 0);

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

    if(TLI_BuildDeviceList() == 0){

        KinesisUtil device_wigner_4("12345897");
        KinesisUtil device_wigner_2("12345897");

        device_wigner_2.load();
        device_wigner_4.load();

        device_wigner_2.startPolling(200);
        device_wigner_4.startPolling(200);

        device_wigner_2.home();
        device_wigner_4.home();

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

                if(fs.is_same_str(recvbuf, "read_data_file")){
                    std::vector<std::string> files = uploadFiles("./data", "bme");
                    for (const auto& file : files) {
                        sendFile(ClientSocket, file);
                    }

                    //Send end-of-transmission marker
                    std::string eotMarker = "EOT";
                    char eotHeader[3];
                    eotHeader[0] = (eotMarker.size() >> 16) & 0xFF;
                    eotHeader[1] = (eotMarker.size() >> 8) & 0xFF;
                    eotHeader[2] = eotMarker.size() & 0xFF;

                    send(ClientSocket, eotHeader, 3, 0);
                    send(ClientSocket, eotMarker.c_str(), eotMarker.size(), 0);
                }

                else if (fs.is_in(recvbuf, "rotate")) {
                    std::istringstream iss(recvbuf);
                    std::string command, deviceName, mode, startTime;
                    double duration = -1.0;
                    bool hasStartTime = false;

                    iss >> command >> deviceName >> mode;

                    if (!(iss >> duration)) {
                        duration = -1.0;  // no duration provided
                    }

                    if (iss >> startTime) {
                        hasStartTime = true;
                    }

                    if (deviceName == "wigner2") {
                        double angle = 0.0;
                        bool runMeasurement = false;

                        if (mode == "full_phase") {
                            // perform full phase scan
                            runMeasurement = true;
                            angle = 0.0;  // could represent starting point
                        } 
                        else if (mode == "fine_scan") {
                            // perform fine scan around optimal point
                            runMeasurement = true;
                            angle = 0.0;
                        } 
                        else {
                            // numeric mode = rotate by given angle
                            try {
                                angle = std::stod(mode);
                            } catch (...) {
                                printf("Invalid angle format: %s\n", mode.c_str());
                            }
                        }

                        // Always rotate first
                        if(!runMeasurement){
                            device_wigner_2.setRelParam(angle);
                            device_wigner_2.moveRel();
                        }

                        if (runMeasurement && duration > 0.0 && hasStartTime) {

                            if(mode == "fine_scan"){
                                device_wigner_2.setRelParam(-10.0);
                                device_wigner_2.moveRel();
                            }

                            // Wait until start time
                            fs.wait_until(startTime.c_str());

                            // Build Python command
                            std::ostringstream pyCmd;
                            pyCmd << "\""
                                << pathbuffer
                                << "\\timestamps_acquisition.py\""
                                << " --duration " << duration;

                            fs.run(pyCmd.str());

                            if(mode == "full_phase"){
                                device_wigner_2.setRelParam(180.0);
                                device_wigner_2.moveRel();
                            }

                            if(mode == "fine_scan"){
                                device_wigner_2.setRelParam(10.0);
                                device_wigner_2.moveRel();
                            }

                            // Clamp collected data
                            std::string end = fs.print_gpstime();
                            clampData("./data", fs.calculate_time_diff(startTime.c_str(), end.c_str()));
                        } else if (!runMeasurement) {
                            printf("Rotation only (no measurement triggered).\n");
                        }
                    }
                    else if (deviceName == "wigner4") {
                        device_wigner_4.setRelParam(0.0);  // placeholder
                        device_wigner_4.moveRel();
                    }
                }*/

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

        device_wigner_2.stopPolling();
        device_wigner_4.stopPolling();
    }

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