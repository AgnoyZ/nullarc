// SPDX-License-Identifier: MIT
#define main psp_fixture_main
#include "psp-fixture.inc"
#undef main

static constexpr uint32_t mailbox[] = {
    PHX_PSP_C2PMSG_64, PHX_PSP_C2PMSG_67, PHX_PSP_C2PMSG_69, PHX_PSP_C2PMSG_70, PHX_PSP_C2PMSG_71,
    PHX_SMU_MSG_REG, PHX_SMU_ARG_REG, PHX_SMU_RESP_REG,
};

static IOReturn send(PhxBringup &d, uint32_t &resp, uint32_t &arg) {
    return d.smuMessage(PHX_PPSMC_GetPmfwVersion, 10, &resp, &arg);
}

static void predecessor() {
    PhxBringup uncaught;
    uint32_t resp = 99, arg = 99;
    CHECK(send(uncaught, resp, arg) == kIOReturnTimeout && !resp && arg == 10);
    CHECK(uncaught.smuPublications == 1 && uncaught.smuArgReads == 1 && !uncaught.exactRawWriters.closed());
    CHECK(uncaught.adoptQueue(queue) == kIOReturnSuccess);

    PhxBringup bypass;
    for (const auto reg : mailbox) {
        unsigned before = bypass.registerWrites;
        CHECK(bypass.writeReg(reg, 0, &arg) == kIOReturnSuccess && bypass.registerWrites == before + 1);
    }
}

static void current() {
    uint32_t resp = 99, arg = 99;
    PhxBringup d;
    for (const auto reg : mailbox) {
        CHECK(d.writeReg(reg, 0, &arg) == kIOReturnNotPermitted);
        CHECK(!d.registerWrites && !d.exactRawWriters.closed() && arg == 99);
    }
    CHECK(d.writeReg(PHX_SMU_MSG_REG + 1, 23, &arg) == kIOReturnSuccess && arg == 23);
    d.smuAck = 1;
    CHECK(send(d, resp, arg) == kIOReturnSuccess && resp == 1 && arg == 17);
    CHECK(d.smuPublications == 1 && d.smuArgReads == 1);
    d.smuAck = 0xff; // an error reply is still an observed reply
    CHECK(send(d, resp, arg) == kIOReturnSuccess && resp == 0xff && arg == 17);
    d.smuResponse = 0;
    CHECK(send(d, resp, arg) == kIOReturnBusy && d.smuPublications == 2 && !d.exactRawWriters.closed());
    d.smuResponse = 1;
    d.smuAck = 0;
    CHECK(send(d, resp, arg) == kIOReturnTimeout && !resp && !arg && d.smuArgReads == 2);
    CHECK(d.smuPublications == 3);
    blocked(d);
    d.smuResponse = 1; // late acknowledgement cannot authorize retry or adoption
    CHECK(send(d, resp, arg) == kIOReturnNotReady && d.smuPublications == 3);
    blocked(d);

    for (const auto ack : {0u, 1u}) {
        PhxBringup race;
        Pause pause;
        uint32_t r = 99, a = 99;
        IOReturn code = -1;
        std::thread sender([&] { firstPoll = &pause; code = send(race, r, a); });
        pause.wait();
        CHECK(race.smuPublications == 1 && race.adoptQueue(queue) == kIOReturnBusy);
        CHECK(race.exactRawWriters.closed() && !race.gpuReady());
        race.smuResponse = ack;
        pause.release();
        sender.join();
        CHECK(code == (ack ? kIOReturnSuccess : kIOReturnTimeout) && r == ack);
        if (ack) CHECK(race.adoptQueue(queue) == kIOReturnSuccess);
        else blocked(race);
    }
}

int main(int argc, char **argv) {
    if (argc == 2 && !std::strcmp(argv[1], "prior")) predecessor();
    else if (argc == 2 && !std::strcmp(argv[1], "psp")) checked();
    else current();
    std::printf("PASS %u firmware checks\n", checks);
}
