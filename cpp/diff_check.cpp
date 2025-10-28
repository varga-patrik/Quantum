#include <iostream>
#include <fstream>
#include <vector>

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: compare_files <original_file> <received_file>\n";
        return 1;
    }

    std::ifstream file1(argv[1], std::ios::binary);
    std::ifstream file2(argv[2], std::ios::binary);

    if (!file1 || !file2) {
        std::cerr << "Error opening files.\n";
        return 1;
    }

    size_t pos = 0;
    char byte1, byte2;
    bool differenceFound = false;

    while (file1.get(byte1) && file2.get(byte2)) {
        if (byte1 != byte2) {
            std::cout << "Difference at byte " << pos
                      << ": original=" << static_cast<int>(static_cast<unsigned char>(byte1))
                      << ", received=" << static_cast<int>(static_cast<unsigned char>(byte2)) << "\n";
            differenceFound = true;
        }
        ++pos;
    }

    if (file1.get(byte1) || file2.get(byte2)) {
        std::cout << "Files have different lengths.\n";
        differenceFound = true;
    }

    if (!differenceFound) {
        std::cout << "Files are identical.\n";
    }

    return 0;
}
