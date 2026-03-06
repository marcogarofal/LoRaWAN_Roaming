import beaker as bk
import pyteal as pt
import _catalogo as ct
from beaker.lib.storage import BoxMapping

# Standardized data structures
class EndpointItem(pt.abi.NamedTuple):
    NetID: pt.abi.Field[pt.abi.String]
    Name_Provider: pt.abi.Field[pt.abi.String]
    Endpoint_SC: pt.abi.Field[pt.abi.Uint64]  # Renamed for consistency

class SLA_output(pt.abi.NamedTuple):
    State_SLA: pt.abi.Field[pt.abi.String]
    Token_broker: pt.abi.Field[pt.abi.String]
    GW_id: pt.abi.Field[pt.abi.String]

class SLAEntry(pt.abi.NamedTuple):
    NetID: pt.abi.Field[pt.abi.String]
    Name_provider: pt.abi.Field[pt.abi.String]
    State_SLA: pt.abi.Field[pt.abi.String]
    Price_contracting: pt.abi.Field[pt.abi.Uint64]
    Threshold_contracting: pt.abi.Field[pt.abi.Uint64]
    Packet_Counter: pt.abi.Field[pt.abi.Uint64]
    Token_broker: pt.abi.Field[pt.abi.String]
    GW_id: pt.abi.Field[pt.abi.String]

class SLA_states:
    sla_entry = BoxMapping(pt.abi.String, SLAEntry)

    App_ID_catalogo = bk.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        descr="catalog endpoint",
    )
    Price_SLA = bk.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        descr="price proposed/accepted during SLA"
    )
    Threshold = bk.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        descr="max number of packets for SLA"
    )
    Tolerance = bk.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(90),  # 90% = 10% tolerance
        descr="percentage tolerance for payments (90 = 90%)"
    )
    Payment_Tolerance = bk.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(95),  # 95% = 5% tolerance
        descr="minimum payment percentage accepted (95 = 95%)"
    )
    Token_broker = bk.GlobalStateValue(
        stack_type=pt.TealType.bytes,
        descr="enable forwarding to sBroker"
    )
    GWid = bk.GlobalStateValue(
        stack_type=pt.TealType.bytes,
        key="GWid",  # Fixed from NetID
        descr="unique identification for a specific Gateway."
    )

app = bk.Application("SLA contracting", state=SLA_states())

####################################### Management functions #################################

@app.create()
def create() -> pt.Expr:
    return pt.Approve()

@app.delete(bare=True, authorize=bk.Authorize.only(pt.Global.creator_address()))
def delete() -> pt.Expr:
    return pt.Approve()

@app.update(bare=True, authorize=bk.Authorize.only(pt.Global.creator_address()))
def update() -> pt.Expr:
    return pt.Reject()

@app.clear_state()
def clear_state() -> pt.Expr:
    return pt.Approve()

@app.opt_in()
def opt_in() -> pt.Expr:
    return pt.Reject()  # No one can use this smart contract via opt-in

@app.close_out(bare=True, authorize=bk.Authorize.opted_in())
def close_out() -> pt.Expr:
    return pt.Approve()

##################################################################################################

####################################### Initialization and Utility functions ###################

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def init(
    app_id_catalog: pt.abi.Uint64,
    price: pt.abi.Uint64,
    threshold: pt.abi.Uint64,
    tolerance: pt.abi.Uint64,
    payment_tolerance: pt.abi.Uint64,
    token: pt.abi.String,
    gwid: pt.abi.String,
    *,
    output: pt.abi.String
) -> pt.Expr:
    return pt.Seq(
        # Input validation
        pt.Assert(app_id_catalog.get() > pt.Int(0), comment="Invalid catalog app ID"),
        pt.Assert(price.get() > pt.Int(0), comment="Price must be greater than 0"),
        pt.Assert(threshold.get() > pt.Int(0), comment="Threshold must be greater than 0"),
        pt.Assert(tolerance.get() <= pt.Int(100), comment="Tolerance must be <= 100%"),
        pt.Assert(payment_tolerance.get() <= pt.Int(100), comment="Payment tolerance must be <= 100%"),

        # Initialization
        app.state.App_ID_catalogo.set(app_id_catalog.get()),
        app.state.Price_SLA.set(price.get()),
        app.state.Threshold.set(threshold.get()),
        app.state.Tolerance.set(tolerance.get()),
        app.state.Payment_Tolerance.set(payment_tolerance.get()),
        app.state.Token_broker.set(token.get()),
        app.state.GWid.set(gwid.get()),

        # Initialization log
        pt.Log(pt.Concat(
            pt.Bytes("SC initialized - GW: "), gwid.get(),
            pt.Bytes(" - Price: "), pt.Itob(price.get())
        )),

        output.set(pt.Bytes("Smart Contract initialized correctly!")),
    )

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def get_appID_cat(*, output: pt.abi.Uint64) -> pt.Expr:
    return pt.Seq(
        pt.If(
            app.state.App_ID_catalogo.exists() == pt.Int(1)
        ).Then(
            output.set(app.state.App_ID_catalogo)
        ).Else(
            output.set(pt.Int(0))
        )
    )

##################################################################################################

####################################### SLA Management functions #################################

@app.external
def getSLA(type_op: pt.abi.String, NetID: pt.abi.String, *, output: SLAEntry) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Or(
                pt.BytesEq(type_op.get(), pt.Bytes("_forward_box")),
                pt.BytesEq(type_op.get(), pt.Bytes("_home_box"))
            ),
            comment="Invalid operation type"
        ),
        (box_name := pt.abi.String()).set(pt.Concat(NetID.get(), type_op.get())),
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1),
            comment="SLA not found"
        ),
        app.state.sla_entry[box_name.get()].store_into(output),
    )

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def deleteSLA(type_op: pt.abi.String, NetID: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Or(
                pt.BytesEq(type_op.get(), pt.Bytes("_forward_box")),
                pt.BytesEq(type_op.get(), pt.Bytes("_home_box"))
            ),
            comment="Invalid operation type"
        ),
        (box_name := pt.abi.String()).set(pt.Concat(NetID.get(), type_op.get())),
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1),
            comment="SLA not found"
        ),

        # Deletion log
        pt.Log(pt.Concat(pt.Bytes("SLA deleted: "), NetID.get(), type_op.get())),

        pt.Pop(app.state.sla_entry[box_name.get()].delete()),
        output.set(pt.Bytes("SLA deleted successfully")),
    )

##################################################################################################

####################################### Core SLA Logic ########################################

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def sla_check(
    NetID_home: pt.abi.String,
    provider: pt.abi.Account,
    cat_ref: pt.abi.Application,
    Name_home_Provider: pt.abi.String,
    Endpoint_home_SC: pt.abi.Application,
    *,
    output: SLA_output
) -> pt.Expr:
    state_SLA = pt.abi.String()
    token = pt.abi.String()
    gw_id = pt.abi.String()
    current_count = pt.abi.Uint64()

    return pt.Seq(
        (box_name := pt.abi.String()).set(pt.Concat(NetID_home.get(), pt.Bytes("_forward_box"))),

        pt.If(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1)
        ).Then(
            # Existing SLA
            (existing_sla_entry := SLAEntry()).decode(app.state.sla_entry[box_name.get()].get()),
            state_SLA.set(existing_sla_entry.State_SLA),
            token.set(existing_sla_entry.Token_broker),
            gw_id.set(existing_sla_entry.GW_id),
            (name_home_Provider := pt.abi.String()).set(existing_sla_entry.Name_provider),
            (price_SLA := pt.abi.Uint64()).set(existing_sla_entry.Price_contracting),
            (threshold_SLA := pt.abi.Uint64()).set(existing_sla_entry.Threshold_contracting),

            pt.If(
                state_SLA.get() == pt.Bytes("Active SLA")
            ).Then(
                current_count.set(existing_sla_entry.Packet_Counter),

                pt.If(
                    current_count.get() == threshold_SLA.get()
                ).Then(
                    # IMPROVED PAYMENT LOGIC
                    (current_balance := pt.abi.Uint64()).set(pt.Balance(pt.Txn.sender())),

                    # Variable to track payment success
                    (payment_successful := pt.abi.Bool()).set(pt.Int(0)),

                    # Execute payment
                    pt.InnerTxnBuilder.ExecuteMethodCall(
                        app_id=Endpoint_home_SC.application_id(),
                        method_signature="pay(application,account)void",
                        args=[cat_ref.application_id(), provider.address()]
                    ),
                    payment_successful.set(pt.Int(1)),  # If we get here, the call succeeded

                    # Payment verification
                    (after_balance := pt.abi.Uint64()).set(pt.Balance(pt.Txn.sender())),
                    (min_expected := pt.abi.Uint64()).set(
                        current_balance.get() + (price_SLA.get() * app.state.Payment_Tolerance / pt.Int(100))
                    ),

                    pt.If(
                        pt.And(
                            payment_successful.get() == pt.Int(1),
                            after_balance.get() >= min_expected.get()
                        )
                    ).Then(
                        # Payment received successfully
                        current_count.set(pt.Int(0)),
                        pt.Log(pt.Concat(
                            pt.Bytes("Payment received from: "), NetID_home.get(),
                            pt.Bytes(" - Amount: "), pt.Itob(after_balance.get() - current_balance.get())
                        )),
                    ).Else(
                        # Insufficient or failed payment
                        state_SLA.set(pt.Bytes("Banned")),
                        pt.Log(pt.Concat(
                            pt.Bytes("Payment failed from: "), NetID_home.get(),
                            pt.Bytes(" - Expected: "), pt.Itob(min_expected.get()),
                            pt.Bytes(" - Received: "), pt.Itob(after_balance.get() - current_balance.get())
                        )),
                    ),
                ).Else(
                    # Increment counter
                    current_count.set(current_count.get() + pt.Int(1)),
                ),

                # Update SLA
                existing_sla_entry.set(
                    NetID_home, name_home_Provider, state_SLA,
                    price_SLA, threshold_SLA, current_count, token, gw_id
                ),
                app.state.sla_entry[box_name.get()].set(existing_sla_entry),

                # Return result
                pt.If(
                    state_SLA.get() == pt.Bytes("Active SLA")
                ).Then(
                    state_SLA.set(pt.Bytes("Accept")),
                    output.set(state_SLA, token, gw_id)
                ).Else(
                    state_SLA.set(pt.Bytes("Reject")),
                    output.set(state_SLA, token, gw_id)
                ),
            ).Else(
                # SLA not active
                state_SLA.set(pt.Bytes("Reject")),
                output.set(state_SLA, token, gw_id),
            ),
        ).Else(
            # New SLA - trigger handshake
            (price_f := pt.abi.Uint64()).set(app.state.Price_SLA),
            (threshold_f := pt.abi.Uint64()).set(app.state.Threshold),

            pt.InnerTxnBuilder.ExecuteMethodCall(
                app_id=Endpoint_home_SC.application_id(),
                method_signature="handshake(application,account,uint64,uint64)(string,string,string)",
                args=[cat_ref.application_id(), provider.address(), price_f, threshold_f]
            ),

            (sla_out := SLA_output()).decode(pt.Suffix(pt.InnerTxn.last_log(), pt.Int(4))),
            state_SLA.set(sla_out.State_SLA),
            token.set(sla_out.Token_broker),
            gw_id.set(sla_out.GW_id),

            # Save new SLA
            (packet_counter_SLA := pt.abi.Uint64()).set(pt.Int(0)),
            (sla_tuple := SLAEntry()).set(
                NetID_home, Name_home_Provider, state_SLA,
                price_f, threshold_f, packet_counter_SLA, token, gw_id
            ),
            app.state.sla_entry[box_name.get()].set(sla_tuple),

            # New SLA log
            pt.Log(pt.Concat(
                pt.Bytes("New SLA created: "), NetID_home.get(),
                pt.Bytes(" - State: "), state_SLA.get()
            )),

            output.decode(pt.Suffix(pt.InnerTxn.last_log(), pt.Int(4)))
        )
    )

@app.external
def handshake(
    app_id_catalog: pt.abi.Application,
    provider: pt.abi.Account,
    price_f: pt.abi.Uint64,
    threshold_f: pt.abi.Uint64,
    *,
    output: SLA_output
) -> pt.Expr:
    state_SLA = pt.abi.String()
    token = pt.abi.String()
    gw_id = pt.abi.String()

    return pt.Seq(
        # Verify catalog app ID
        pt.Assert(
            app_id_catalog.application_id() == app.state.App_ID_catalogo,
            comment="Invalid catalog app ID"
        ),

        # Contact catalog
        pt.InnerTxnBuilder.ExecuteMethodCall(
            app_id=app_id_catalog.application_id(),
            method_signature=ct.get_entry_provider.method_signature(),
            args=[provider]
        ),

        (catalogo_entry := EndpointItem()).decode(pt.Suffix(pt.InnerTxn.last_log(), pt.Int(4))),
        (NetID_forwarder := pt.abi.String()).set(catalogo_entry.NetID),
        (Name_Provider_forwarder := pt.abi.String()).set(catalogo_entry.Name_Provider),
        (Endpoint_SC_forwarder := pt.abi.Uint64()).set(catalogo_entry.Endpoint_SC),

        # Verify caller is correct
        pt.Assert(
            pt.Global.caller_app_id() == Endpoint_SC_forwarder.get(),
            comment="Caller app ID mismatch"
        ),

        # Verify SLA doesn't already exist
        (box_name := pt.abi.String()).set(pt.Concat(NetID_forwarder.get(), pt.Bytes("_home_box"))),
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(0),
            comment="SLA already exists"
        ),

        # SLA negotiation
        pt.If(
            pt.And(
                app.state.Price_SLA >= price_f.get(),
                threshold_f.get() >= app.state.Threshold,
            )
        ).Then(
            token.set(app.state.Token_broker),
            gw_id.set(app.state.GWid),
            state_SLA.set(pt.Bytes("Active SLA")),

            pt.Log(pt.Concat(
                pt.Bytes("SLA accepted: "), NetID_forwarder.get(),
                pt.Bytes(" - Price: "), pt.Itob(price_f.get()),
                pt.Bytes(" - Threshold: "), pt.Itob(threshold_f.get())
            )),
        ).Else(
            token.set(pt.Bytes("None")),
            gw_id.set(pt.Bytes("None")),
            state_SLA.set(pt.Bytes("SLA rejected")),

            pt.Log(pt.Concat(
                pt.Bytes("SLA rejected: "), NetID_forwarder.get(),
                pt.Bytes(" - Price offered: "), pt.Itob(price_f.get()),
                pt.Bytes(" - Price required: "), pt.Itob(app.state.Price_SLA)
            )),
        ),

        # Save SLA
        (packet_counter_SLA := pt.abi.Uint64()).set(pt.Int(0)),
        (sla_tuple := SLAEntry()).set(
            NetID_forwarder, Name_Provider_forwarder, state_SLA,
            price_f, threshold_f, packet_counter_SLA, token, gw_id
        ),
        app.state.sla_entry[box_name.get()].set(sla_tuple),

        output.set(state_SLA, token, gw_id)
    )

##################################################################################################

####################################### Packet and Payment Management ###########################

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def receive_packet_from_forwarder(NetID_forwarder: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    state_SLA = pt.abi.String()
    current_count = pt.abi.Uint64()

    return pt.Seq(
        (box_name := pt.abi.String()).set(pt.Concat(NetID_forwarder.get(), pt.Bytes("_home_box"))),

        # Verify SLA existence and status
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1),
            comment="SLA not found"
        ),

        (existing_sla_entry := SLAEntry()).decode(app.state.sla_entry[box_name.get()].get()),
        state_SLA.set(existing_sla_entry.State_SLA),

        pt.Assert(
            state_SLA.get() == pt.Bytes("Active SLA"),
            comment="SLA not active"
        ),

        # Increment counter
        (name_home_Provider := pt.abi.String()).set(existing_sla_entry.Name_provider),
        (price_SLA := pt.abi.Uint64()).set(existing_sla_entry.Price_contracting),
        (threshold_SLA := pt.abi.Uint64()).set(existing_sla_entry.Threshold_contracting),
        (token := pt.abi.String()).set(existing_sla_entry.Token_broker),
        (gw_id := pt.abi.String()).set(existing_sla_entry.GW_id),
        current_count.set(existing_sla_entry.Packet_Counter),

        current_count.set(current_count.get() + pt.Int(1)),

        # Update SLA
        existing_sla_entry.set(
            NetID_forwarder, name_home_Provider, state_SLA,
            price_SLA, threshold_SLA, current_count, token, gw_id
        ),
        app.state.sla_entry[box_name.get()].set(existing_sla_entry),

        # Packet received log
        pt.Log(pt.Concat(
            pt.Bytes("Packet received from: "), NetID_forwarder.get(),
            pt.Bytes(" - Count: "), pt.Itob(current_count.get()),
            pt.Bytes("/"), pt.Itob(threshold_SLA.get())
        )),

        output.set(pt.Bytes("Packet received"))
    )

@app.external()
def pay(app_id_catalog: pt.abi.Application, receiver: pt.abi.Account) -> pt.Expr:
    return pt.Seq(
        # Verify catalog app ID
        pt.Assert(
            app_id_catalog.application_id() == app.state.App_ID_catalogo,
            comment="Invalid catalog app ID"
        ),

        # Contact catalog
        pt.InnerTxnBuilder.ExecuteMethodCall(
            app_id=app_id_catalog.application_id(),
            method_signature=ct.get_entry_provider.method_signature(),
            args=[receiver]
        ),

        (catalogo_entry := EndpointItem()).decode(pt.Suffix(pt.InnerTxn.last_log(), pt.Int(4))),
        (NetID_forwarder := pt.abi.String()).set(catalogo_entry.NetID),
        (Endpoint_SC_forwarder := pt.abi.Uint64()).set(catalogo_entry.Endpoint_SC),

        # Verify caller
        pt.Assert(
            pt.Global.caller_app_id() == Endpoint_SC_forwarder.get(),
            comment="Caller app ID mismatch"
        ),

        (box_name := pt.abi.String()).set(pt.Concat(NetID_forwarder.get(), pt.Bytes("_home_box"))),

        # Verify SLA
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1),
            comment="SLA not found"
        ),

        (existing_sla_entry := SLAEntry()).decode(app.state.sla_entry[box_name.get()].get()),
        (state_SLA := pt.abi.String()).set(existing_sla_entry.State_SLA),
        (name_forwarder_Provider := pt.abi.String()).set(existing_sla_entry.Name_provider),
        (price_SLA := pt.abi.Uint64()).set(existing_sla_entry.Price_contracting),
        (threshold_SLA := pt.abi.Uint64()).set(existing_sla_entry.Threshold_contracting),
        (current_count := pt.abi.Uint64()).set(existing_sla_entry.Packet_Counter),
        (token := pt.abi.String()).set(existing_sla_entry.Token_broker),
        (gw_id := pt.abi.String()).set(existing_sla_entry.GW_id),

        # Verify payment conditions
        (min_packets := pt.abi.Uint64()).set(
            (threshold_SLA.get() * app.state.Tolerance) / pt.Int(100)
        ),

        pt.If(
            pt.And(
                current_count.get() >= min_packets.get(),
                state_SLA.get() == pt.Bytes("Active SLA")
            )
        ).Then(
            # Execute payment
            pt.InnerTxnBuilder.Execute(
                {
                    pt.TxnField.type_enum: pt.TxnType.Payment,
                    pt.TxnField.amount: price_SLA.get(),
                    pt.TxnField.receiver: receiver.address(),
                }
            ),

            # Reset counter
            current_count.set(pt.Int(0)),
            (sla_tuple := SLAEntry()).set(
                NetID_forwarder, name_forwarder_Provider, state_SLA,
                price_SLA, threshold_SLA, current_count, token, gw_id
            ),
            app.state.sla_entry[box_name.get()].set(sla_tuple),

            # Payment log
            pt.Log(pt.Concat(
                pt.Bytes("Payment sent to: "), NetID_forwarder.get(),
                pt.Bytes(" - Amount: "), pt.Itob(price_SLA.get()),
                pt.Bytes(" - Packets: "), pt.Itob(current_count.get())
            )),
        ),
    )

##################################################################################################

####################################### Utility and Admin functions ############################

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def balance(receiver: pt.abi.Account, *, output: pt.abi.Uint64) -> pt.Expr:
    return output.set(pt.Balance(receiver.address()))

@app.external(authorize=bk.Authorize.only(pt.Global.creator_address()))
def ban_home_function(NetID_forwarder: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    state_SLA = pt.abi.String()
    current_count = pt.abi.Uint64()

    return pt.Seq(
        (box_name := pt.abi.String()).set(pt.Concat(NetID_forwarder.get(), pt.Bytes("_home_box"))),

        # Verify existing SLA
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1),
            comment="SLA not found"
        ),

        (existing_sla_entry := SLAEntry()).decode(app.state.sla_entry[box_name.get()].get()),
        state_SLA.set(existing_sla_entry.State_SLA),

        pt.Assert(
            state_SLA.get() == pt.Bytes("Active SLA"),
            comment="SLA not active"
        ),

        # Update to banned
        (name_home_Provider := pt.abi.String()).set(existing_sla_entry.Name_provider),
        (price_SLA := pt.abi.Uint64()).set(existing_sla_entry.Price_contracting),
        (threshold_SLA := pt.abi.Uint64()).set(existing_sla_entry.Threshold_contracting),
        (token := pt.abi.String()).set(existing_sla_entry.Token_broker),
        (gw_id := pt.abi.String()).set(existing_sla_entry.GW_id),
        current_count.set(existing_sla_entry.Packet_Counter),

        state_SLA.set(pt.Bytes("Banned")),

        # Update SLA
        existing_sla_entry.set(
            NetID_forwarder, name_home_Provider, state_SLA,
            price_SLA, threshold_SLA, current_count, token, gw_id
        ),
        app.state.sla_entry[box_name.get()].set(existing_sla_entry),

        # Ban log
        pt.Log(pt.Concat(
            pt.Bytes("Provider banned: "), NetID_forwarder.get(),
            pt.Bytes(" - Reason: Manual ban")
        )),

        output.set(pt.Bytes("Provider banned successfully")),
    )

# Function to get SLA statistics
@app.external(read_only=True)
def get_sla_stats(NetID: pt.abi.String, type_op: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Or(
                pt.BytesEq(type_op.get(), pt.Bytes("_forward_box")),
                pt.BytesEq(type_op.get(), pt.Bytes("_home_box"))
            ),
            comment="Invalid operation type"
        ),
        (box_name := pt.abi.String()).set(pt.Concat(NetID.get(), type_op.get())),
        pt.Assert(
            app.state.sla_entry[box_name.get()].exists() == pt.Int(1),
            comment="SLA not found"
        ),

        (existing_sla_entry := SLAEntry()).decode(app.state.sla_entry[box_name.get()].get()),

        # Extract values from ABI fields
        (netid_val := pt.abi.String()).set(existing_sla_entry.NetID),
        (state_val := pt.abi.String()).set(existing_sla_entry.State_SLA),
        (count_val := pt.abi.Uint64()).set(existing_sla_entry.Packet_Counter),
        (threshold_val := pt.abi.Uint64()).set(existing_sla_entry.Threshold_contracting),
        (price_val := pt.abi.Uint64()).set(existing_sla_entry.Price_contracting),

        # Build statistics string
        output.set(pt.Concat(
            pt.Bytes("NetID:"), netid_val.get(),
            pt.Bytes("|State:"), state_val.get(),
            pt.Bytes("|Count:"), pt.Itob(count_val.get()),
            pt.Bytes("|Threshold:"), pt.Itob(threshold_val.get()),
            pt.Bytes("|Price:"), pt.Itob(price_val.get())
        ))
    )

##################################################################################################

if __name__ == "__main__":
    app.build().export("./SC/artifacts")
