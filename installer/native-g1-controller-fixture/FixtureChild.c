#define WIN32_LEAN_AND_MEAN
#include <windows.h>

/* Fixed CI-only native fixture. No CRT, arguments, files, sockets or plugins.
   This is a containment probe, never a replacement Grid Coordinator/Worker. */
void WINAPI FixtureEntry(void)
{
    ExitProcess(0);
}
