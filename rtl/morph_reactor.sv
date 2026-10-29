module morph_reactor (
    input  logic clk,
    input  logic rst_n,
    input  logic pin_in,
    output logic pin_out,
    output logic event_seen
);

logic pin_prev;
logic [2:0] timer;
logic state;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        pin_prev   <= 1'b0;
        pin_out    <= 1'b0;
        event_seen <= 1'b0;
        timer      <= 3'd0;
        state      <= 1'b0;
    end else begin
        pin_prev   <= pin_in;
        event_seen <= 1'b0;

        if (!state) begin
            if (pin_in && !pin_prev) begin
                state      <= 1'b1;
                timer      <= 3'd0;
                event_seen <= 1'b1;
            end
        end else begin
            if (timer == 3'd3) begin
                pin_out <= ~pin_out;
                timer   <= 3'd0;
                state   <= 1'b0;
            end else begin
                timer <= timer + 1'b1;
            end
        end
    end
end

endmodule