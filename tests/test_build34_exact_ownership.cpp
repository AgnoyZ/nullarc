// SPDX-License-Identifier: MIT
// CPU state-contract tests of the unintegrated R3 ownership prototype.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <random>
#include <thread>
#include <vector>
#include "build34_exact_ownership.h"

using namespace phx34_exact;
static std::atomic<unsigned> checks;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"check failed at %d: %s\n",__LINE__,#x); std::abort(); } } while (0)

static Ticket publish(Registry &registry, uint64_t seq, unsigned queue=0, uint64_t gen=1) {
    Ticket t;
    CHECK(registry.reserve(t)==Status::Ok);
    CHECK(registry.publish(t,Receipt{seq,gen,queue})==Status::Ok);
    return t;
}
static void no_output_change(Ticket a, Ticket b) {
    CHECK(a.owner==b.owner && a.serial==b.serial && a.slot==b.slot);
}

static void identity_and_admission() {
    Counter ids;
    uint64_t owner=0;
    CHECK(ids.take(owner) && owner==1);
    Registry r(owner), other(2), zero(0), sentinel(UINT64_MAX);
    Ticket unchanged{99,88,77}, t=unchanged;
    CHECK(zero.reserve(t)==Status::Closed); no_output_change(t,unchanged);
    CHECK(sentinel.reserve(t)==Status::Closed); no_output_change(t,unchanged);
    CHECK(r.lookup(20,t)==Status::Unknown); no_output_change(t,unchanged);
    CHECK(r.lookup(0,t)==Status::Invalid && r.lookup(UINT64_MAX,t)==Status::Invalid);
    no_output_change(t,unchanged);
    CHECK(r.reserve(t)==Status::Ok && r.occupied()==1);
    QueueObservation q[2]={{1,20,20,true,false},{1,0,0,true,false}};
    CHECK(r.observe(t,true,q)==Status::Unsubmitted);
    CHECK(r.forget(t)==Status::Invalid);
    const Receipt bad[]={{0,1,0},{UINT64_MAX,1,0},{20,0,0},{20,UINT64_MAX,0},{20,1,2}};
    for (auto receipt:bad) CHECK(r.publish(t,receipt)==Status::Invalid && r.occupied()==1);
    CHECK(other.publish(t,Receipt{20,1,0})==Status::Unknown);
    CHECK(r.publish(t,Receipt{20,1,0})==Status::Ok);
    CHECK(r.publish(t,Receipt{21,1,0})==Status::Invalid);
    CHECK(r.cancel(t)==Status::Invalid);
    CHECK(other.observe(t,true,q)==Status::Unknown);
    Ticket foreign=t; foreign.owner=2;
    CHECK(r.observe(foreign,true,q)==Status::Unknown);
    foreign=t; foreign.serial++;
    CHECK(r.observe(foreign,true,q)==Status::Unknown);
    foreign=t; foreign.slot=Registry::capacity;
    CHECK(r.observe(foreign,true,q)==Status::Unknown);
    Ticket found=unchanged;
    CHECK(r.lookup(15,found)==Status::Unknown); no_output_change(found,unchanged);
    CHECK(r.lookup(20,found)==Status::Ok); no_output_change(found,t);
    CHECK(r.observe(t,true,q)==Status::Complete && r.forget(t)==Status::Ok);
    CHECK(r.lookup(20,found)==Status::Unknown && r.observe(t,true,q)==Status::Unknown);
    CHECK(r.reserve(found)==Status::Ok && found.slot==t.slot && found.serial!=t.serial);
    CHECK(r.publish(found,Receipt{20,1,0})==Status::Invalid); // no sequence ABA after forgetting
    CHECK(r.publish(found,Receipt{19,1,0})==Status::Invalid);
    CHECK(r.cancel(found)==Status::Ok && r.occupied()==0);
    CHECK(r.cancel(found)==Status::Unknown);
    Counter edge(UINT64_MAX-2);
    uint64_t value=5;
    CHECK(edge.take(value) && value==UINT64_MAX-1);
    value=123;
    CHECK(!edge.take(value) && value==123);
    CHECK(!edge.take(value) && value==123);
    Counter invalid(UINT64_MAX);
    CHECK(!invalid.take(value) && value==123);
}

static void exact_gaps_and_history_reuse() {
    for (unsigned gap=0; gap<128; ++gap) {
        Registry a(10+gap*2), b(11+gap*2);
        const uint64_t seq=gap&1 ? UINT64_MAX-10000+gap*3 : 100+gap*3;
        Ticket early=publish(a,seq), late=publish(b,seq+1,1);
        QueueObservation q[2]={{1,seq,seq-1,true,false},{1,seq+1,seq+1,true,false}};
        CHECK(a.observe(early,true,q)==Status::Pending);
        CHECK(b.observe(late,true,q)==Status::Complete);
        Ticket miss;
        CHECK(a.lookup(seq+1,miss)==Status::Unknown && b.lookup(seq,miss)==Status::Unknown);
        // Queue histories may have reused all 64 slots many times. A retained
        // receipt still identifies its actual queue and epoch, without a slot.
        q[1].submitted=q[1].completed=seq+5000;
        CHECK(b.observe(late,true,q)==Status::Complete);
        CHECK(a.observe(early,true,q)==Status::Pending);
        q[0].completed=seq;
        CHECK(a.observe(early,true,q)==Status::Complete);
        CHECK(a.forget(early)==Status::Ok && b.forget(late)==Status::Ok);
        CHECK(a.observe(early,true,q)==Status::Unknown);
    }
}

static void capacity_and_lease_reuse() {
    Registry r(300);
    std::vector<Ticket> held;
    for (unsigned i=0;i<Registry::capacity;++i) held.push_back(publish(r,20+i,i&1));
    Ticket unchanged{5,6,7}, t=unchanged;
    CHECK(r.occupied()==Registry::capacity && r.reserve(t)==Status::Full);
    no_output_change(t,unchanged);
    QueueObservation q[2]={{1,100,0,true,false},{1,100,0,true,false}};
    for (auto lease:held) {
        CHECK(r.observe(lease,true,q)==Status::Pending);
        CHECK(r.forget(lease)==Status::Invalid && r.cancel(lease)==Status::Invalid);
    }
    q[1].completed=100;
    CHECK(r.observe(held[1],true,q)==Status::Complete);
    CHECK(r.forget(held[1])==Status::Ok && r.occupied()==Registry::capacity-1);
    Ticket replacement=publish(r,101,1);
    CHECK(replacement.slot==held[1].slot && replacement.serial!=held[1].serial);
    CHECK(r.cancel(held[1])==Status::Unknown && r.forget(held[1])==Status::Unknown);
    CHECK(r.observe(held[1],true,q)==Status::Unknown);
    q[1].submitted=101;
    CHECK(r.observe(replacement,true,q)==Status::Pending);
    q[1].completed=101;
    CHECK(r.observe(replacement,true,q)==Status::Complete);
    CHECK(r.forget(replacement)==Status::Ok);
    // Reserved metadata can be cancelled before publication and reused safely.
    CHECK(r.reserve(t)==Status::Ok && r.cancel(t)==Status::Ok);
    CHECK(r.observe(t,true,q)==Status::Unknown);
    // Losing a queue generation retains its uncertain receipts; a full ledger
    // must not overwrite them to admit work from the replacement generation.
    q[0].generation=q[1].generation=2;
    for (unsigned i=0;i<held.size();++i) {
        if (i==1) continue;
        CHECK(r.observe(held[i],true,q)==Status::Lost);
        CHECK(r.forget(held[i])==Status::Invalid);
    }
    Ticket new_generation=publish(r,102,1,2);
    CHECK(r.reserve(t)==Status::Full && r.occupied()==Registry::capacity);
    CHECK(r.observe(new_generation,true,q)==Status::InvalidObservation);
}

static void generation_fault_close_and_bad_observation() {
    for (unsigned mode=0;mode<6;++mode) {
        Registry r(400+mode);
        Ticket t=publish(r,20,1,7);
        QueueObservation q[2]={{1,100,100,true,false},{7,20,19,true,false}};
        CHECK(r.observe(t,true,q)==Status::Pending);
        bool live=true;
        if (mode==0) q[1].generation=8;
        if (mode==1) q[1].ready=false;
        if (mode==2) q[1].faulted=true;
        if (mode==3) live=false;
        if (mode==4) q[1].generation=0;
        if (mode==5) q[1].generation=UINT64_MAX;
        q[1].completed=20; // seeded/high fences never override identity loss
        CHECK(r.observe(t,live,q)==Status::Lost);
        q[1]={7,20,20,true,false};
        CHECK(r.observe(t,true,q)==Status::Lost); // loss is sticky
        CHECK(r.forget(t)==Status::Invalid && r.cancel(t)==Status::Invalid && r.occupied()==1);
        Ticket found;
        CHECK(r.lookup(20,found)==Status::Ok); no_output_change(found,t);
        r.close(); r.close();
        CHECK(r.observe(t,true,q)==Status::Closed);
        CHECK(r.lookup(20,found)==Status::Closed && r.occupied()==1);
        CHECK(r.forget(t)==Status::Closed && r.cancel(t)==Status::Closed);
        CHECK(r.reserve(found)==Status::Closed);
        CHECK(r.publish(t,Receipt{21,7,1})==Status::Closed);
    }
    Registry r(500);
    Ticket t=publish(r,20);
    QueueObservation q[2]={{1,19,19,true,false},{1,100,100,true,false}};
    CHECK(r.observe(t,true,q)==Status::InvalidObservation);
    q[0]={1,20,21,true,false};
    CHECK(r.observe(t,true,q)==Status::InvalidObservation);
    q[0]={1,UINT64_MAX,20,true,false};
    CHECK(r.observe(t,true,q)==Status::InvalidObservation);
    q[0]={1,20,19,true,false};
    CHECK(r.observe(t,true,q)==Status::Pending);
    q[0].completed=20;
    CHECK(r.observe(t,true,q)==Status::Complete);
    q[0].completed=19;
    CHECK(r.observe(t,true,q)==Status::InvalidObservation);
    CHECK(r.forget(t)==Status::Ok); // a prior valid completion still exists
    CHECK(r.occupied()==0);
    Registry old_owner(600);
    Ticket old_client=publish(old_owner,21);
    old_owner.close();
    Registry replacement_client(601);
    Ticket new_client=publish(replacement_client,21);
    CHECK(new_client.slot==old_client.slot && new_client.serial==old_client.serial && new_client.owner!=old_client.owner);
    CHECK(replacement_client.observe(old_client,true,q)==Status::Unknown);
    q[0]={1,21,20,true,false};
    CHECK(replacement_client.observe(new_client,true,q)==Status::Pending);
}

// Independent reference: maps of issued submissions by owner and actual queue;
// reference completion is membership in a set built from each queue's prefix.
static void model_comparison() {
    std::mt19937 rng(0x34e0);
    for (unsigned round=0;round<128;++round) {
        Registry a(1000+round*2), b(1001+round*2);
        Registry *registries[2]={&a,&b};
        struct Work { unsigned owner, queue; uint64_t sequence; Ticket ticket; };
        std::vector<Work> work;
        std::vector<uint64_t> queues[2];
        uint64_t sequence=round&1 ? UINT64_MAX-1000 : 1000;
        for (unsigned i=0;i<64;++i) {
            unsigned owner=rng()%2, queue=rng()%2;
            sequence+=1+rng()%3;
            Ticket t=publish(*registries[owner],sequence,queue,9+queue);
            work.push_back({owner,queue,sequence,t});
            queues[queue].push_back(sequence);
        }
        for (unsigned step=0;step<9;++step) {
            std::map<uint64_t,bool> completed;
            QueueObservation observations[2];
            for (unsigned queue=0;queue<2;++queue) {
                size_t count=step*queues[queue].size()/8;
                for (size_t i=0;i<count;++i) completed[queues[queue][i]]=true;
                observations[queue]={9+queue,queues[queue].empty()?0:queues[queue].back(),
                    count?queues[queue][count-1]:0,true,false};
            }
            for (auto entry:work) {
                auto &owner=*registries[entry.owner];
                auto &foreign=*registries[!entry.owner];
                Ticket found;
                CHECK(owner.lookup(entry.sequence,found)==Status::Ok);
                no_output_change(found,entry.ticket);
                CHECK(foreign.lookup(entry.sequence,found)==Status::Unknown);
                const bool done=completed.count(entry.sequence)!=0;
                CHECK(owner.observe(entry.ticket,true,observations)==(done?Status::Complete:Status::Pending));
            }
        }
        for (auto entry:work) CHECK(registries[entry.owner]->forget(entry.ticket)==Status::Ok);
        CHECK(a.occupied()==0 && b.occupied()==0);
    }
}

static void callback_ticket_reuse_and_close() {
    for (unsigned mode=0;mode<3;++mode) {
        Registry r(2000+mode);
        Ticket original=publish(r,20), replacement;
        QueueObservation q[2]={{1,20,20,true,false},{1,0,0,true,false}};
        std::mutex mutex;
        std::condition_variable condition;
        bool entered=false, resume=false;
        Status result=Status::Invalid;
        std::thread waiter([&] {
            Ticket snapshot;
            {
                std::lock_guard<std::mutex> lock(mutex);
                CHECK(r.lookup(20,snapshot)==Status::Ok);
                entered=true; condition.notify_all();
            }
            // Stand-in for a native callback without retaining Entry pointers.
            std::unique_lock<std::mutex> lock(mutex);
            CHECK(condition.wait_for(lock,std::chrono::seconds(5),[&]{return resume;}));
            result=r.observe(snapshot,true,q);
        });
        {
            std::unique_lock<std::mutex> lock(mutex);
            CHECK(condition.wait_for(lock,std::chrono::seconds(5),[&]{return entered;}));
            if (mode==0) {
                CHECK(r.observe(original,true,q)==Status::Complete && r.forget(original)==Status::Ok);
                replacement=publish(r,21);
                q[0].submitted=21;
            } else if (mode==1) {
                r.close();
            } else {
                q[0].generation=2;
            }
            resume=true; condition.notify_all();
        }
        waiter.join();
        CHECK(result==(mode==0?Status::Unknown:mode==1?Status::Closed:Status::Lost));
        if (mode==0) CHECK(r.observe(replacement,true,q)==Status::Pending);
        CHECK(r.occupied()==1);
    }
}

int main() {
    identity_and_admission();
    exact_gaps_and_history_reuse();
    capacity_and_lease_reuse();
    generation_fault_close_and_bad_observation();
    model_comparison();
    callback_ticket_reuse_and_close();
    std::printf("PASS R3 ownership prototype: %u checks; 128 gaps, 128 independent model rounds, bounded admission, epochs, reuse, close, three callback interleavings; GPU_executed=false\n",checks.load());
}
