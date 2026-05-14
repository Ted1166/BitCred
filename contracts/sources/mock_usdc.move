module bitcred::mock_usdc {
    use sui::coin::{Self, Coin, TreasuryCap};
    use sui::table::{Self, Table};
    use sui::clock::{Self, Clock};

    const CLAIM_AMOUNT: u64 = 10_000_000_000;
    const CLAIM_COOLDOWN_MS: u64 = 86_400_000;
    const ECooldown: u64 = 0;

    public struct MOCK_USDC has drop {}

    public struct USDCFaucet has key {
        id: UID,
        treasury: TreasuryCap<MOCK_USDC>,
        last_claim: Table<address, u64>
    }

    public struct Claimed has copy, drop {
        user: address,
        amount: u64
    }

    fun init(witness: MOCK_USDC, ctx: &mut TxContext) {
        let (treasury, metadata) = coin::create_currency(
            witness,
            6,
            b"USDC",
            b"Mock USDC Coin",
            b"Testnet USDC for BitCred",
            option::none(),
            ctx
        );
        transfer::public_freeze_object(metadata);
        transfer::share_object(USDCFaucet {
            id: object ::new(ctx),
            treasury,
            last_claim: table::new(ctx)
        });
    }

    public fun claim(faucet: &mut USDCFaucet, clock: &Clock, ctx: &mut TxContext): Coin<MOCK_USDC> {
        let caller = ctx.sender();
        let now = clock::timestamp_ms(clock);
        if (table::contains(&faucet.last_claim, caller)) {
            let last = *table::borrow(&faucet.last_claim,caller);
            assert!(now - last >= CLAIM_COOLDOWN_MS,ECooldown);
            *table::borrow_mut(&mut faucet.last_claim, caller) = now;
        } else {
            table::add(&mut faucet.last_claim, caller, now);
        };

        sui::event::emit(Claimed {user: caller, amount: CLAIM_AMOUNT});
        coin::mint(&mut faucet.treasury, CLAIM_AMOUNT, ctx)
    }

    public fun time_until_next_claim(faucet: &USDCFaucet, clock: &Clock, user: address): u64 {
        if (!table::contains(&faucet.last_claim, user)) {return 0};
        let last = *table::borrow(&faucet.last_claim, user);
        let now = clock::timestamp_ms(clock);
        if (now >= last + CLAIM_COOLDOWN_MS) {0} else {(last + CLAIM_COOLDOWN_MS) - now}
    }
}