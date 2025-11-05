cmake_minimum_required(VERSION 3.15)
project(Quantum LANGUAGES CXX)

# --- Set compiler standard ---
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- Include directories ---
include_directories(
    ${CMAKE_SOURCE_DIR}/cpp
    ${CMAKE_SOURCE_DIR}/cpp/Correlator
    ${CMAKE_SOURCE_DIR}/cpp/data_collection
    ${CMAKE_SOURCE_DIR}/cpp/fs740
    ${CMAKE_SOURCE_DIR}/cpp/kinesis
    ${CMAKE_SOURCE_DIR}/cpp/orchestrator
    "C:/Program Files/Thorlabs/Kinesis"
    "C:/Users/Varga Patrik/Desktop/util/fftw-3.3.5-dll64"
)

# --- Collect source files ---
file(GLOB_RECURSE allSources
    "${CMAKE_SOURCE_DIR}/cpp/*.cpp"
)

# --- Create executable ---
add_executable(tcpClient ${allSources})

# --- Link libraries ---
target_link_libraries(tcpClient
    PRIVATE
        "C:/Program Files/Thorlabs/Kinesis/Thorlabs.MotionControl.IntegratedStepperMotors.lib"
        "C:/Users/Varga Patrik/Desktop/util/fftw-3.3.5-dll64/libfftw3-3.a"
)

# --- Copy DLLs after build ---
add_custom_command(TARGET tcpClient POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "C:/Program Files/Thorlabs/Kinesis/Thorlabs.MotionControl.IntegratedStepperMotors.dll"
        $<TARGET_FILE_DIR:tcpClient>
)
add_custom_command(TARGET tcpClient POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "C:/Users/Varga Patrik/Desktop/util/fftw-3.3.5-dll64/libfftw3-3.dll"
        $<TARGET_FILE_DIR:tcpClient>
)
