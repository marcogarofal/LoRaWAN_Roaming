import beaker as bk
import pyteal as pt


PAYMENT_AMT = pt.Int(1000000) # 1 million microAlgos = 1 Algo
ALGO_PARTICIPATION_AMT = 1 # INCREMENT OR DECREMENT FOR PARTICIPATION TO THE ROAMING SYSTEM

# Standardized definition of EndpointItem structure
class EndpointItem(pt.abi.NamedTuple):
    NetID: pt.abi.Field[pt.abi.String]
    Name_Provider: pt.abi.Field[pt.abi.String]
    Endpoint_SC: pt.abi.Field[pt.abi.Uint64]  # Renamed for consistency


class Endpoint_list:
    ##################################
    # Local State
    # 16 key-value pairs per account
    # 128 bytes each
    # Users must opt in before using
    ##################################

    # NetID: identify of provider in LoRaWAN network
    NetID = bk.LocalStateValue(
        stack_type=pt.TealType.bytes,
        key="NetID",
        descr="Identify of provider in LoRaWAN network."
    )

    # Name_Provider: name of the provider who participated in the ecosystem
    Name_Provider = bk.LocalStateValue(
        stack_type=pt.TealType.bytes,
        key="Provider Name",
        default=pt.Bytes(""),
        descr="Name of the provider who participated in the ecosystem."
    )

    # Endpoint_SC: Endpoint smart contract entry of the provider that are part of the ecosystem
    Endpoint_SC = bk.LocalStateValue(
        stack_type=pt.TealType.uint64,
        key="Endpoint of Smart Contract",
        default=pt.Int(0),
        descr="Endpoint Smart Contract of the provider that are part of the ecosystem.",
    )


app = bk.Application("List of endpoint", state=Endpoint_list())

####################################### LoRA Management function #################################

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
##################################################################################################

####################################### Provider Management function #############################
@app.opt_in()
def opt_in(payment: pt.abi.PaymentTransaction) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            payment.get().receiver() == pt.Global.creator_address(),
            comment="The receiver of payment is incorrect!"
        ),
        pt.Assert(
            payment.get().amount() >= (PAYMENT_AMT * pt.Int(ALGO_PARTICIPATION_AMT)),
            comment="The amount of payment is too low!"
        ),
        app.initialize_local_state(),
    )

@app.close_out(bare=True, authorize=bk.Authorize.opted_in())
def close_out() -> pt.Expr:
    return pt.Approve()
##################################################################################################

####################################### Provider function ########################################

@app.external(authorize=bk.Authorize.opted_in())
def set_entry_provider(
    NetID_Provider: pt.abi.String,
    Name_Provider: pt.abi.String,
    app_id_SC_Provider: pt.abi.Uint64,
    *,
    output: pt.abi.String
) -> pt.Expr:
    return pt.Seq(
        # Input validation
        pt.Assert(
            pt.Len(NetID_Provider.get()) > pt.Int(0),
            comment="NetID cannot be empty"
        ),
        pt.Assert(
            pt.Len(Name_Provider.get()) > pt.Int(0),
            comment="Provider name cannot be empty"
        ),
        pt.Assert(
            app_id_SC_Provider.get() > pt.Int(0),
            comment="App ID must be greater than 0"
        ),

        # Setting values
        app.state.NetID[pt.Txn.sender()].set(NetID_Provider.get()),
        app.state.Name_Provider[pt.Txn.sender()].set(Name_Provider.get()),
        app.state.Endpoint_SC[pt.Txn.sender()].set(app_id_SC_Provider.get()),

        # Operation log
        pt.Log(pt.Concat(
            pt.Bytes("Provider registered: "),
            NetID_Provider.get(),
            pt.Bytes(" - "),
            Name_Provider.get()
        )),

        output.set(pt.Bytes("Endpoint registered successfully!")),
    )

@app.external(read_only=True)
def get_entry_provider(provider: pt.abi.Account, *, output: EndpointItem) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            app.state.Endpoint_SC[provider.address()].exists() == pt.Int(1),
            comment="This provider not found!"
        ),
        (NetID_output := pt.abi.String()).set(app.state.NetID[provider.address()]),  # Fixed typo
        (Name_Provider_output := pt.abi.String()).set(app.state.Name_Provider[provider.address()]),
        (Endpoint_SC_output := pt.abi.Uint64()).set(app.state.Endpoint_SC[provider.address()]),
        output.set(NetID_output, Name_Provider_output, Endpoint_SC_output)
    )

@app.external(authorize=bk.Authorize.opted_in())
def delete_endpoint(*, output: pt.abi.String) -> pt.Expr:
    return pt.Seq(
        # Check if the provider has set the endpoint in the catalog
        pt.Assert(
            app.state.Endpoint_SC[pt.Txn.sender()].exists() == pt.Int(1),
            comment="This provider not found!"
        ),

        # Log before deletion
        pt.Log(pt.Concat(
            pt.Bytes("Provider deleted: "),
            app.state.NetID[pt.Txn.sender()].get()
        )),

        # Deletion
        app.state.NetID[pt.Txn.sender()].delete(),
        app.state.Name_Provider[pt.Txn.sender()].delete(),
        app.state.Endpoint_SC[pt.Txn.sender()].delete(),

        output.set(pt.Bytes("Endpoint deleted successfully!")),
    )

# Utility function to check if a provider exists
@app.external(read_only=True)
def provider_exists(provider: pt.abi.Account, *, output: pt.abi.Bool) -> pt.Expr:
    return output.set(app.state.Endpoint_SC[provider.address()].exists())

##################################################################################################


if __name__ == "__main__":
    app.build().export("./catalogo/artifacts")
