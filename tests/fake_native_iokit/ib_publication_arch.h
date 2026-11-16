// Test-only CPU capability/operation hooks; never execute real cache instructions.
#ifndef PHX_IB_PUBLICATION_ARCH_H
#define PHX_IB_PUBLICATION_ARCH_H
bool phxIbClflushCapability(unsigned *lineBytes);
void phxIbClflushLine(const volatile void *line);
void phxIbPublicationFence();
#endif
