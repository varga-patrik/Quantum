#include <iostream>
#include <fstream>
#include <vector>
#include "Correlator.h"
#include <filesystem>

//Delta T = 81.358.000
//Delta T = 82.296.000

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
    Correlator correlator(100000, (1ULL << 20));

    correlator.Tshift = 0;

    std::vector<std::string> files_bme = collectFiles("../data", "timestamps_bme");
    std::vector<std::string> files_wigner = collectFiles("../data", "timestamps_wigner");

    correlator.runCorrelation(true, files_bme, files_wigner, 2048);
}
