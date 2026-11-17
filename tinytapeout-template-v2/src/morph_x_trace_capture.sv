`default_nettype none

// MORPH X trace prototype: captures 8 changed-input events after two flip-flop
// synchronizer stages. External read mode pauses capture and re-primes the
// edge detector; this deliberately does NOT promise gap-free streaming.
module morph_x_trace_capture (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    input  wire       program_mode,
    input  wire       read_mode,
    input  wire [7:0] sample_pins,
    input  wire [2:0] read_slot,
    input  wire [1:0] read_page,
    output reg  [7:0] read_data,
    output wire [7:0] status
);
    (* ASYNC_REG = "TRUE" *) reg [7:0] pin_meta;
    (* ASYNC_REG = "TRUE" *) reg [7:0] pin_sync;
    reg [7:0] previous;
    reg [15:0] ticks;
    reg [3:0] event_count;
    reg overflow;
    reg primed;
    reg [31:0] events [0:7];

    wire [7:0] changes = pin_sync ^ previous;
    wire full = (event_count == 4'd8);

    // status[3:0]=count (0..8), [4]=overflow,
    // [5]=full, [6]=sampling primed, [7]=reserved.
    assign status = {1'b0, primed, full, overflow, event_count};

    always @(posedge clk) begin
        pin_meta <= sample_pins;
        pin_sync <= pin_meta;
        if (!rst_n || program_mode) begin
            ticks <= 16'd0;
            previous <= pin_sync;
            event_count <= 4'd0;
            overflow <= 1'b0;
            primed <= 1'b0;
        end else if (!enable || read_mode) begin
            // Host reads are consistent: pause recording and don't synthesize
            // a false edge when returning to execution mode.
            previous <= pin_sync;
            primed <= 1'b0;
        end else if (!primed) begin
            previous <= pin_sync;
            primed <= 1'b1;
        end else begin
            ticks <= ticks + 16'd1;
            previous <= pin_sync;
            if (changes != 8'h00) begin
                if (!full) begin
                    // [31:16] capture time; [15:8] changed pins;
                    // [7:0] synchronized levels.
                    events[event_count[2:0]] <= {ticks, changes, pin_sync};
                    event_count <= event_count + 4'd1;
                end else begin
                    overflow <= 1'b1;
                end
            end
        end
    end

    always @* begin
        read_data = 8'h00;
        if ({1'b0, read_slot} < event_count) begin
            case (read_page)
                2'd0: read_data = events[read_slot][7:0];
                2'd1: read_data = events[read_slot][15:8];
                2'd2: read_data = events[read_slot][23:16];
                2'd3: read_data = events[read_slot][31:24];
                default: read_data = 8'h00;
            endcase
        end
    end
endmodule

`default_nettype wire
