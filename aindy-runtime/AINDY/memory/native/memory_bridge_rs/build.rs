fn main() {
    // Compile the C++ semantic engine into a static library that Rust links against.
    // Uses the cc crate (no proc-macros, no cxxbridge) — compatible with Windows
    // Application Control environments where only established toolchain executables
    // (cl.exe, link.exe) are whitelisted.
    cc::Build::new()
        .file("memory_cpp/semantic.cpp")
        .include("memory_cpp")
        .cpp(true)
        // Windows MSVC
        .flag_if_supported("/std:c++17")
        .flag_if_supported("/O2")
        // GCC / Clang (MinGW, WSL, Linux CI)
        .flag_if_supported("-std=c++17")
        .flag_if_supported("-O3")
        .flag_if_supported("-march=native")
        .compile("semantic");

    println!("cargo:rerun-if-changed=memory_cpp/semantic.cpp");
    println!("cargo:rerun-if-changed=memory_cpp/semantic.h");
}
