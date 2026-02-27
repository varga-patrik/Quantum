#include <iostream>
#include <fstream>
#include <vector>
#include "fs_util.h"
#include "Correlator.h"
#include <filesystem>

//2^24
//max(S) = 14.282766, kmax = 50622
//Delta T = 103.673856 microsec

//2^23
//max(S) = 9.202164, kmax = 50622
//Delta T = 103.673856 microsec

//2^22
//max(S) = 6.703411, kmax = 50622
//Delta T = 103.673856 microsec

//2^21
//max(S) = 5.150041, kmax = 1610403
//Delta T = 3298.105344 microsec

//2^20
//max(S) = 4.920758, kmax = 831269
//Delta T = 1702.438912 microsec

std::vector<std::string> collectFiles(const std::string& folder, const std::string& condition) {
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

int main(int argc, char* argv[]) {
    Correlator correlator(100000, (1ULL << 23));

    correlator.Tshift = 0;

    std::vector<std::string> files_bme = collectFiles("../data", "timestamps_bme_02-20_10-49");
    std::vector<std::string> files_wigner = collectFiles("../data", "timestamps_wigner_02-20_10-49");

    correlator.runCorrelation(false, files_bme, files_wigner, 2048);
}
